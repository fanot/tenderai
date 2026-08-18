/* ============================================================
   Офлайн-движок TenderAI.

   Портирует ключевую логику backend'а (разбор запроса, BM25,
   фильтры, реранк, экстрактивный ответ ассистента) на JS, чтобы
   прототип можно было показать одним HTML-файлом, без сервера.

   Источник данных — window.__EMBEDDED_TENDERS__ (внедряется
   скриптом scripts/build_standalone.py).
   ============================================================ */
window.Offline = (function(){
  const T = () => window.__EMBEDDED_TENDERS__ || [];
  const TODAY = new Date();
  const day = 86400000;
  const daysLeft = d => Math.round((new Date(d) - TODAY)/day);

  /* ---------- текст ---------- */
  const STOP = new Set(['и','в','во','не','что','на','с','со','как','а','то','все','так','его','но','по','за','от','из','для','о','у','к','до','или','при','это','эти','мы','я']);
  const norm = s => (s||'').toLowerCase().replace(/ё/g,'е');
  function tokens(s){
    return norm(s).match(/[а-яa-z0-9]+/g)?.filter(t=>t.length>1 && !STOP.has(t)).map(stem) || [];
  }
  const SUF = ['иями','ями','ами','иях','ах','ях','ов','ев','ий','ый','ой','ая','ое','ые','ых','ым','ем','ом','ам','ую','юю','ее','ие','ия','ью','ья','ей','ми','ть','ся','ет','ут','ют','ат','ят','ал','ил','ла','ло','ли','на','ны','у','ю','а','я','о','е','и','ы','ь','й'];
  function stem(t){
    if(t.length<=4 || /^\d+$/.test(t)) return t;
    for(const s of SUF) if(t.endsWith(s) && t.length-s.length>=4) return t.slice(0,-s.length);
    return t;
  }

  /* ---------- разбор запроса ---------- */
  const REGIONS = [
    ['Московская область', /московск\w*\s+обл|подмосковь\w*/],
    ['г. Москва', /\bмоскв\w*|\bмск\b/],
    ['г. Санкт-Петербург', /санкт[- ]петербург\w*|\bспб\b|петербург\w*|питер\w*/],
    ['Свердловская область', /свердловск\w*|екатеринбург\w*/],
    ['Республика Татарстан', /татарстан\w*|казан\w*/],
    ['Новосибирская область', /новосибирск\w*/],
    ['Краснодарский край', /краснодар\w*|кубан\w*/],
    ['Нижегородская область', /нижегородск\w*|нижн\w*\s+новгород\w*/],
    ['Челябинская область', /челябинск\w*/],
    ['Воронежская область', /воронеж\w*/],
    ['Красноярский край', /красноярск\w*/],
    ['Самарская область', /самар\w*/],
  ];
  const CATS = {
    'ИТ и разработка ПО': [/\bит\b/,/\bit\b/,/софт\w*/,/программн\w*/,/разработк\w*/,/сайт\w*/,/информационн\w*\s+систем\w*/,/мобильн\w*\s+приложен\w*/,/цифров\w*/],
    'Поставка вычислительной техники': [/компьютер\w*/,/ноутбук\w*/,/сервер\w*/,/оргтехник\w*/,/монитор\w*/,/\bмфу\b/,/вычислительн\w*/,/принтер\w*/],
    'Строительство и ремонт': [/строительств\w*/,/ремонт\w*/,/капремонт\w*/,/благоустройств\w*/,/подряд\w*/,/\bсро\b/],
    'Медицина и фармацевтика': [/медицин\w*/,/медицинск\w*/,/лекарств\w*/,/фарм\w*/,/больниц\w*/,/здравоохранен\w*/,/препарат\w*/],
    'Транспорт и логистика': [/транспорт\w*/,/перевозк\w*/,/логистик\w*/,/автобус\w*/,/груз\w*/],
    'Продукты питания': [/питани\w*/,/продукт\w*/,/молочн\w*/,/столов\w*/],
    'Клининг и эксплуатация': [/уборк\w*/,/клининг\w*/,/эксплуатац\w*/,/санитарн\w*/],
    'Охрана и безопасность': [/охран\w*/,/безопасност\w*/,/видеонаблюден\w*/,/\bчоп\b/],
    'Образование и обучение': [/образован\w*/,/обучен\w*/,/квалификац\w*/,/учебн\w*/,/тренинг\w*/],
    'Энергетика и ЖКХ': [/энерг\w*/,/\bжкх\b/,/электрич\w*/,/тепло\w*/,/инженерн\w*\s+сет\w*/],
  };
  const MULT = [[/млрд|миллиард\w*/,1e9],[/млн|миллион\w*/,1e6],[/тыс\w*/,1e3]];
  const AMT = String.raw`(\d[\d\s]*(?:[.,]\d+)?)\s*(млрд|млн|тыс[а-я]*|миллион[а-я]*|миллиард[а-я]*)?`;

  function amount(num, unit){
    let v = parseFloat(String(num).replace(/\s/g,'').replace(',','.'));
    if(unit) for(const [re,m] of MULT) if(re.test(unit)) return v*m;
    return v;
  }

  function parse(raw){
    const q = norm(raw||'');
    const p = {raw:raw||'', text:'', law:null, region:null, category:null,
               nmck_min:null, nmck_max:null, smp_only:null, only_active:false, matched:[]};
    if(/44[\s-]*фз/.test(q)){ p.law='44-ФЗ'; p.matched.push('закон 44-ФЗ'); }
    else if(/223[\s-]*фз/.test(q)){ p.law='223-ФЗ'; p.matched.push('закон 223-ФЗ'); }
    if(/\bсмп\b|мал\w* предприним|субъект\w* мал/.test(q)){ p.smp_only=true; p.matched.push('только для СМП'); }
    if(/актуальн|действующ|открыт|подача заяв|сейчас|принима/.test(q)){ p.only_active=true; p.matched.push('только приём заявок'); }

    const fmt = v => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:0}).format(v);
    const range = q.match(new RegExp(`от\\s+${AMT}\\s+до\\s+${AMT}`));
    if(range){
      p.nmck_min = amount(range[1],range[2]); p.nmck_max = amount(range[3],range[4]);
      p.matched.push(`НМЦК ${fmt(p.nmck_min)}–${fmt(p.nmck_max)} ₽`);
    } else {
      const mx = q.match(new RegExp(`(?:до|не более|дешевле|менее|максимум)\\s+${AMT}`));
      if(mx && (mx[2] || amount(mx[1],null)>=1000)){ p.nmck_max = amount(mx[1],mx[2]); p.matched.push(`НМЦК до ${fmt(p.nmck_max)} ₽`); }
      const mn = q.match(new RegExp(`(?:от|не менее|дороже|более|свыше|больше)\\s+${AMT}`));
      if(mn && (mn[2] || amount(mn[1],null)>=1000)){ p.nmck_min = amount(mn[1],mn[2]); p.matched.push(`НМЦК от ${fmt(p.nmck_min)} ₽`); }
    }
    for(const [name,re] of REGIONS) if(re.test(q)){ p.region=name; p.matched.push('регион: '+name); break; }
    let best=null,bestN=0;
    for(const [cat,res] of Object.entries(CATS)){
      const n = res.filter(r=>r.test(q)).length;
      if(n>bestN){ best=cat; bestN=n; }
    }
    if(best){ p.category=best; p.matched.push('категория: '+best); }

    let cleaned = q.replace(/44[\s-]*фз|223[\s-]*фз/g,' ')
                   .replace(new RegExp(`(?:от|до|не более|не менее|свыше|менее|более)\\s+${AMT}`,'g'),' ')
                   .replace(/\b(найди|найти|ищу|искать|покажи|показать|нужн\w*|хочу|подбер\w*|выведи|госзакупк\w*|закупк\w*|тендер\w*|аукцион\w*|пожалуйста|какие)\w*/g,' ')
                   .replace(/\s+/g,' ').trim();
    p.text = cleaned || (raw||'').trim();
    return p;
  }

  /* ---------- индекс ---------- */
  let IDX = null;
  function blob(t){
    return [t.subject, t.customer, t.region, t.category, t.law, t.procedure, t.platform,
            t.okpd2, t.registry_number, t.requirements.join(' '), t.advantages, t.description].join(' ');
  }
  function index(){
    if(IDX) return IDX;
    const docs = T().map(t => ({t, toks: tokens(blob(t))}));
    const df = new Map();
    docs.forEach(d => new Set(d.toks).forEach(tok => df.set(tok,(df.get(tok)||0)+1)));
    const avgdl = docs.reduce((s,d)=>s+d.toks.length,0)/(docs.length||1);
    docs.forEach(d => {
      d.tf = new Map();
      d.toks.forEach(tok => d.tf.set(tok,(d.tf.get(tok)||0)+1));
    });
    IDX = {docs, df, avgdl, N: docs.length};
    return IDX;
  }
  function bm25(query){
    const {docs, df, avgdl, N} = index();
    const qt = tokens(query);
    if(!qt.length) return docs.map(d=>({t:d.t, s:0}));
    const k1=1.5, b=0.75;
    return docs.map(d => {
      let s=0;
      for(const tok of new Set(qt)){
        const n = df.get(tok)||0; if(!n) continue;
        const tf = d.tf.get(tok)||0; if(!tf) continue;
        const idf = Math.log(1 + (N-n+0.5)/(n+0.5));
        s += idf * (tf*(k1+1)) / (tf + k1*(1-b+b*d.toks.length/avgdl));
      }
      return {t:d.t, s};
    });
  }

  function passes(t,p,f){
    const law = f.law||p.law, region=f.region||p.region, cat=f.category||p.category;
    const min = f.nmck_min??p.nmck_min, max = f.nmck_max??p.nmck_max;
    const smp = f.smp_only??p.smp_only, act = f.only_active||p.only_active;
    if(law && t.law!==law) return false;
    if(region && t.region!==region) return false;
    if(cat && t.category!==cat) return false;
    if(f.status && t.status!==f.status) return false;
    if(min!=null && t.nmck<min) return false;
    if(max!=null && t.nmck>max) return false;
    if(smp && !t.smp_only) return false;
    if(act && t.status!=='Подача заявок') return false;
    return true;
  }

  function rank(query, filters){
    const p = parse(query);
    const f = filters||{};
    const scored = bm25(p.text || p.raw);
    const maxS = Math.max(1e-9, ...scored.map(x=>x.s));
    const out = [];
    for(const {t,s} of scored){
      if(!passes(t,p,f)) continue;
      const explain=[]; let boost=1;
      if(t.status==='Подача заявок'){ boost+=0.25; explain.push('приём заявок открыт'); }
      const dl = daysLeft(t.deadline_at);
      if(dl>=0 && dl<=7){ boost+=0.10; explain.push(`дедлайн через ${dl} дн.`); }
      const age = Math.round((TODAY-new Date(t.published_at))/day);
      boost += Math.max(0, 0.15*(1-age/60));
      if((f.category||p.category)===t.category){ boost+=0.10; explain.push('совпадение по категории'); }
      if((f.region||p.region)===t.region){ boost+=0.05; explain.push('совпадение по региону'); }
      out.push({t, score: (0.02 + s/maxS)*boost, explain});
    }
    out.sort((a,b)=>b.score-a.score);
    return {parsed:p, hits:out};
  }

  /* ---------- публичное API (совместимо с backend) ---------- */
  function row(h){
    const t=h.t;
    return {
      id:t.id, registry_number:t.registry_number, subject:t.subject, customer:t.customer,
      region:t.region, category:t.category, law:t.law, procedure:t.procedure, platform:t.platform,
      nmck:t.nmck, published_at:t.published_at, deadline_at:t.deadline_at,
      days_left:daysLeft(t.deadline_at), status:t.status, smp_only:t.smp_only, url:t.url,
      score:h.score, explain:h.explain,
      snippet:t.description.slice(0,260),
    };
  }

  const SORT = {
    relevance:(a,b)=>b.score-a.score,
    deadline:(a,b)=>a.deadline_at.localeCompare(b.deadline_at),
    nmck_desc:(a,b)=>b.nmck-a.nmck,
    nmck_asc:(a,b)=>a.nmck-b.nmck,
    published:(a,b)=>b.published_at.localeCompare(a.published_at),
  };

  function search(body){
    const t0 = performance.now();
    const {parsed, hits} = rank(body.query, body.filters||{});
    let rows = hits.map(row);
    rows.sort(SORT[body.sort]||SORT.relevance);
    const start = Math.max(0,(body.page-1)*body.page_size);
    return {
      total: rows.length, page: body.page, page_size: body.page_size,
      took_ms: +(performance.now()-t0).toFixed(2),
      parsed_filters: parsed, applied_filters: parsed,
      results: rows.slice(start, start+body.page_size),
    };
  }

  function tender(id){
    const t = T().find(x=>x.id===id);
    const sim = rank(t.subject, {category:t.category}).hits.filter(h=>h.t.id!==id).slice(0,4)
      .map(h=>({id:h.t.id, subject:h.t.subject, nmck:h.t.nmck, region:h.t.region, deadline_at:h.t.deadline_at}));
    return Object.assign({}, t, {days_left:daysLeft(t.deadline_at), similar:sim});
  }

  const money = v => new Intl.NumberFormat('ru-RU',{maximumFractionDigits:2}).format(v)+' ₽';

  /* Вопрос без предмета закупки («какие требования?») наследует контекст
     текущего поискового запроса — так же, как в backend'е. */
  function inheritContext(p, contextQuery){
    if(!contextQuery || !contextQuery.trim()) return p;
    const c = parse(contextQuery);
    ['law','region','category','nmck_min','nmck_max','smp_only'].forEach(f=>{
      if(p[f]==null) p[f]=c[f];
    });
    if(!p.only_active) p.only_active = c.only_active;
    c.matched.forEach(m=>{ if(!p.matched.includes(m)) p.matched.push(m); });
    if(p.text.split(/\s+/).filter(Boolean).length < 2 && c.text) p.text = (c.text+' '+p.text).trim();
    return p;
  }

  function rankWithContext(query, contextQuery){
    const p = inheritContext(parse(query), contextQuery);
    const scored = bm25(p.text || p.raw);
    const maxS = Math.max(1e-9, ...scored.map(x=>x.s));
    const out = [];
    for(const {t,s} of scored){
      if(!passes(t,p,{})) continue;
      const explain=[]; let boost=1;
      if(t.status==='Подача заявок'){ boost+=0.25; explain.push('приём заявок открыт'); }
      const dl = daysLeft(t.deadline_at);
      if(dl>=0 && dl<=7){ boost+=0.10; explain.push(`дедлайн через ${dl} дн.`); }
      if(p.category===t.category) boost+=0.10;
      if(p.region===t.region) boost+=0.05;
      out.push({t, score:(0.02 + s/maxS)*boost, explain});
    }
    out.sort((a,b)=>b.score-a.score);
    return {parsed:p, hits:out};
  }

  function ask(query, contextQuery){
    const t0 = performance.now();
    const {parsed, hits} = rankWithContext(query, contextQuery);
    const top = hits.slice(0,8);
    const q = norm(query);
    let intent = 'search';
    if(/требован|документ|лиценз|сро|допуск|что нужно|условия участ/.test(q)) intent='requirements';
    else if(/дедлайн|срок|когда|до какого|успе/.test(q)) intent='deadline';
    else if(/нмцк|цена|стоимост|бюджет|сколько сто|демпинг/.test(q)) intent='price';
    else if(/сколько всего|статистик|аналитик|распредел|топ |средн/.test(q)) intent='analytics';

    const sources = top.map((h,i)=>({
      n:i+1, tender_id:h.t.id, registry_number:h.t.registry_number, title:h.t.subject,
      section:'Карточка закупки', snippet:h.t.description.slice(0,300), url:h.t.url,
    }));

    let lines;
    if(!top.length){
      lines = ['По заданным условиям подходящих закупок не найдено. Попробуйте расширить бюджетный диапазон, убрать фильтр по региону или сформулировать предмет закупки короче.'];
    } else {
      const head = parsed.matched.length ? parsed.matched.join(', ') : 'без дополнительных фильтров';
      lines = [`Нашёл ${hits.length} подходящих закупок (${head}).`, ''];
      if(intent==='requirements'){
        lines.push('Ключевые требования к участникам по найденным закупкам:');
        top.slice(0,5).forEach((h,i)=>lines.push(`• ${h.t.subject} — ${h.t.requirements.slice(0,3).join('; ')} [${i+1}]`));
        lines.push('', 'Общее для всех закупок: отсутствие в РНП, отсутствие налоговой задолженности, соответствие ст. 31 44-ФЗ.');
      } else if(intent==='deadline'){
        lines.push('Ближайшие сроки подачи заявок:');
        [...top].sort((a,b)=>a.t.deadline_at.localeCompare(b.t.deadline_at)).slice(0,5).forEach(h=>{
          const n = top.indexOf(h)+1, d = daysLeft(h.t.deadline_at);
          lines.push(`• до ${h.t.deadline_at} (${d>=0?'осталось '+d+' дн.':'приём завершён'}) — ${h.t.subject} [${n}]`);
        });
      } else if(intent==='price'){
        const v = top.map(h=>h.t.nmck);
        const avg = v.reduce((a,b)=>a+b,0)/v.length;
        lines.push(`Диапазон НМЦК: от ${money(Math.min(...v))} до ${money(Math.max(...v))}, среднее — ${money(avg)}.`, '');
        [...top].sort((a,b)=>b.t.nmck-a.t.nmck).slice(0,5).forEach(h=>lines.push(`• ${money(h.t.nmck)} — ${h.t.subject} [${top.indexOf(h)+1}]`));
      } else if(intent==='analytics'){
        const cat={}, reg={};
        top.forEach(h=>{cat[h.t.category]=(cat[h.t.category]||0)+1; reg[h.t.region]=(reg[h.t.region]||0)+1;});
        lines.push(`Суммарная НМЦК по выборке: ${money(top.reduce((s,h)=>s+h.t.nmck,0))}.`);
        lines.push('Категории: '+Object.entries(cat).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([k,v])=>`${k} — ${v}`).join(', ')+'.');
        lines.push('Регионы: '+Object.entries(reg).sort((a,b)=>b[1]-a[1]).slice(0,3).map(([k,v])=>`${k} — ${v}`).join(', ')+'.', '');
        top.slice(0,3).forEach((h,i)=>lines.push(`• ${h.t.subject} [${i+1}]`));
      } else {
        lines.push('Наиболее релевантные позиции:');
        top.slice(0,5).forEach((h,i)=>{
          const d = daysLeft(h.t.deadline_at);
          const why = h.explain.length?h.explain.join(', '):'совпадение по тексту закупки';
          lines.push(`${i+1}. ${h.t.subject} — ${h.t.customer}, ${h.t.region}. НМЦК ${money(h.t.nmck)}, ${h.t.law}, заявки до ${h.t.deadline_at}${d>=0?` (осталось ${d} дн.)`:''}. Почему в подборке: ${why}. [${i+1}]`);
        });
      }
      lines.push('', 'Проверьте документацию на площадке перед подачей заявки: сведения приведены по данным карточек закупок и не являются юридической консультацией.');
    }

    const answer = lines.join('\n');
    const cited = new Set([...answer.matchAll(/\[(\d+)\]/g)].map(m=>+m[1]));
    const valid = new Set(sources.map(s=>s.n));
    const warnings = [...cited].filter(n=>!valid.has(n)).length
      ? ['Ответ ссылается на несуществующие источники'] : [];

    return {answer, intent, provider:'local (offline)', filters:parsed, sources, warnings,
            took_ms:+(performance.now()-t0).toFixed(2)};
  }

  function meta(){
    const u = f => [...new Set(T().map(t=>t[f]))].sort();
    return {
      total:T().length, categories:u('category'), regions:u('region'), laws:u('law'),
      statuses:u('status'), platforms:u('platform'), procedures:u('procedure'),
      nmck_min:Math.min(...T().map(t=>t.nmck)), nmck_max:Math.max(...T().map(t=>t.nmck)),
      embeddings_provider:'local (offline)', llm_provider:'local (offline)',
      chunks:T().length*3, index_build_ms:0,
    };
  }

  function analytics(){
    const t = T();
    const cat={}, reg={}, law={};
    t.forEach(x=>{
      cat[x.category]=cat[x.category]||{count:0,nmck:0}; cat[x.category].count++; cat[x.category].nmck+=x.nmck;
      reg[x.region]=(reg[x.region]||0)+1; law[x.law]=(law[x.law]||0)+1;
    });
    const active = t.filter(x=>x.status==='Подача заявок');
    return {
      total:t.length, active:active.length,
      total_nmck:t.reduce((s,x)=>s+x.nmck,0),
      avg_nmck:t.reduce((s,x)=>s+x.nmck,0)/t.length,
      smp_share:+(100*t.filter(x=>x.smp_only).length/t.length).toFixed(1),
      by_category:Object.entries(cat).map(([k,v])=>({category:k,count:v.count,nmck:v.nmck})).sort((a,b)=>b.count-a.count),
      by_region:Object.entries(reg).map(([k,v])=>({region:k,count:v})).sort((a,b)=>b.count-a.count),
      by_law:law,
      closing_soon:active.filter(x=>daysLeft(x.deadline_at)>=0&&daysLeft(x.deadline_at)<=7)
        .sort((a,b)=>a.deadline_at.localeCompare(b.deadline_at)).slice(0,5)
        .map(x=>({id:x.id,subject:x.subject,deadline_at:x.deadline_at,nmck:x.nmck,days_left:daysLeft(x.deadline_at)})),
    };
  }

  return {parse, search, tender, ask, meta, analytics};
})();
