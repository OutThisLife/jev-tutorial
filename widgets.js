// Widgets for the tutorial. Every Jev number comes from window.JEV (widget-data.js),
// which build_widgets.py writes from the real results in cases/ and design/.
const D = window.JEV;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const fillOf = r => r.style.setProperty('--fill', `${((r.value - r.min) / (r.max - r.min)) * 100}%`);
const setText = (sel, root, t) => { const el = $(sel, root); if (el) el.textContent = t; };
const f2 = p => p.toFixed(2);
const esc = s => s.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]);
const band = (p, yes = 0.8, no = 0.35) => (p >= yes ? 'take' : p >= no ? 'unsure' : 'skip');
const chip = (p, cls = band(p)) => `<span class="chip ${cls}">${f2(p)}</span>`;
const meter = p => `<span class="bar" style="--w:${Math.round(p * 100)}%"></span>`;
const row = (label, p, cls) => `<div class="wrow"><span class="lab">${label}</span><span>${meter(p)}${chip(p, cls)}</span></div>`;

function seg(root, onPick) {
  const btns = $$('button', root);
  const pick = b => { btns.forEach(x => x.setAttribute('aria-pressed', x === b)); onPick(b); };
  btns.forEach(b => b.addEventListener('click', () => pick(b)));
  return { btns, pick };
}

// Substring check vs Jev's real answer, on the hand-written agent summaries
(() => {
  const w = $('#w-parse'); if (!w) return;
  const box = $('.chips', w), quote = $('[data-quote]', w), rule = $('[data-rule]', w), jev = $('[data-jev]', w);
  box.innerHTML = D.verdicts.map((v, i) => `<button data-i="${i}">${esc(v.text)}</button>`).join('');
  const say = { take: 'ready to move on', unsure: 'not sure, ask a person', skip: 'not done' };
  const { btns, pick } = seg(box, b => {
    const v = D.verdicts[+b.dataset.i];
    quote.textContent = v.done ? 'Really done' : 'Not actually done';
    rule.innerHTML = `<span class="chip ${v.substring ? 'take' : 'skip'}">${v.substring ? 'counts as a pass' : 'counts as a fail'}</span>`
      + (v.substring !== v.done ? '<span class="dim">wrong</span>' : '');
    jev.innerHTML = `${meter(v.jev)}${chip(v.jev)}<span class="dim">${say[band(v.jev)]}</span>`;
  });
  pick(btns[D.verdicts.findIndex(v => v.text.includes('NOT PASS'))]);
})();

// Confidence vs the winning probability, with TypeSafe's choice formula
(() => {
  const w = $('#w-conf'); if (!w) return;
  const sliders = $$('input[type=range]', w), outs = $$('[data-opt]', w), keys = Object.keys(D.conf.choice);
  const keys2 = keys, total = 100;
  const render = () => {
    const p = sliders.map(s => +s.value / total), n = p.length;
    const conf = (Math.max(...p) - 1 / n) / (1 - 1 / n), top = p.indexOf(Math.max(...p));
    outs.forEach((o, i) => { o.textContent = f2(p[i]); });
    $('[data-conf]', w).textContent = f2(Math.max(0, conf));
    $('[data-top]', w).textContent = `${sliders[top].getAttribute('aria-label')} wins with ${f2(p[top])}`;
  };
  // moving one slider rescales the others, so the three always add up to 1
  const rebalance = moved => {
    const v = +moved.value, rest = sliders.filter(s => s !== moved), was = rest.reduce((a, s) => a + +s.value, 0);
    rest.forEach(s => { s.value = was > 0 ? Math.round((+s.value / was) * (total - v)) : Math.round((total - v) / rest.length); });
    const drift = total - sliders.reduce((a, s) => a + +s.value, 0);
    if (drift) rest[0].value = +rest[0].value + drift;
    sliders.forEach(fillOf);
  };
  const set = vals => { sliders.forEach((s, i) => { s.value = vals[i]; fillOf(s); }); render(); };
  const reset = () => {
    const raw = keys2.map(k => Math.round(D.conf.choice[k] * total)), d = total - raw.reduce((a, b) => a + b, 0);
    raw[raw.indexOf(Math.max(...raw))] += d; set(raw);
  };
  sliders.forEach(s => s.addEventListener('input', () => { rebalance(s); render(); }));
  $('[data-reset]', w).addEventListener('click', reset);
  setText('[data-title]', w, D.conf.title);
  reset();
})();

// Three bands, with presets for how costly a mistake is
(() => {
  const w = $('.bands'); if (!w) return;
  const r = $('#p', w), pv = $('#pv', w), verdict = $('#pverdict', w), why = $('#pwhy', w);
  let yes = 0.8, no = 0.35;
  const render = () => {
    const p = +r.value;
    pv.textContent = f2(p);
    const [label, color, text] =
      p >= yes ? ['go this way', 'var(--accent)', 'Confident yes: take this path.']
      : p >= no ? ['not sure', 'var(--unsure-ink)', 'Unsure: stop and ask a person.']
      : ['skip', 'var(--muted)', 'Confident no: try the next path.'];
    verdict.textContent = label; verdict.style.color = color; why.textContent = text;
  };
  seg($('.seg', w), b => {
    no = +b.dataset.no; yes = +b.dataset.yes;
    w.style.setProperty('--no', `${no * 100}%`); w.style.setProperty('--yes', `${yes * 100}%`);
    $('[data-lno]', w).textContent = `no below ${f2(no)}`;
    $('[data-lyes]', w).textContent = `yes from ${f2(yes)}`;
    $('[data-cost]', w).textContent = b.dataset.cost;
    render();
  });
  r.addEventListener('input', render);
  render();
})();

// Fan-out: measured Jev latency by number of questions, vs a measured LLM call per question
(() => {
  const w = $('#w-fan'); if (!w) return;
  const r = $('input', w), pts = D.fan.points, AGENT = D.fan.llm_ms / 1000;
  const jevAt = k => {  // straight line between the measured medians
    const i = Math.max(1, pts.findIndex(([n]) => n >= k)), [n0, m0] = pts[i - 1], [n1, m1] = pts[i] || pts[i - 1];
    return (n1 === n0 ? m0 : m0 + ((m1 - m0) * (k - n0)) / (n1 - n0)) / 1000;
  };
  const render = () => {
    const k = +r.value, agent = k * AGENT, jev = jevAt(k), MAX = +r.max * AGENT;
    $('[data-n]', w).textContent = `${k} question${k > 1 ? 's' : ''} about one change`;
    $('[data-agent]', w).innerHTML = Array.from({ length: k }, () => `<i style="width:${(AGENT / MAX) * 100}%"></i>`).join('');
    $('[data-jev]', w).innerHTML = `<i class="one" style="width:${(jev / MAX) * 100}%"></i>`;
    $('[data-at]', w).textContent = `${agent.toFixed(1)} s`;
    $('[data-jt]', w).textContent = `${jev.toFixed(2)} s`;
  };
  r.max = pts[pts.length - 1][0];
  setText('[data-llm]', w, f2(AGENT).replace(/0$/, ''));
  setText('[data-pts]', w, pts.map(([n, ms]) => `${ms} ms for ${n}`).join(', '));
  r.addEventListener('input', render);
  render();
})();

// One multiple-choice question vs a yes/no question for each, on real pull requests
(() => {
  const w = $('#w-split'); if (!w) return;
  const ex = D.split.examples, Q = { auth: 'touches auth', no_tests: 'adds no tests' };
  const notes = [
    'Both are true, but as one choice Jev splits its belief and neither clears 0.8.',
    'Both are true, but the choice puts nearly everything on one, so a gate would miss the other.',
  ];
  seg($('.seg', w), b => {
    const e = ex[+b.dataset.i];
    $('[data-title]', w).textContent = e.title;
    $('[data-choice]', w).innerHTML = [...Object.keys(Q), 'neither'].map(k => row(Q[k] || 'neither', e.choice[k])).join('');
    $('[data-noul]', w).innerHTML = Object.keys(Q).map(k => row(Q[k], e.nouls[k])).join('');
    $('[data-note]', w).textContent = notes[+b.dataset.i];
  }).pick($('.seg button', w));
  setText('[data-count]', w, `${D.split.n_hurt} of ${D.split.n_both}`);
})();

// Step through a gate, on real pull requests and Jev's real answers
(() => {
  const w = $('#w-gate'); if (!w) return;
  const PATHS = [
    { id: 'catalog', kind: 'judgement', name: 'Only adds a catalog entry', to: 'Quick catalog checks' },
    { id: 'security', kind: 'judgement', name: 'Touches auth or secrets', to: 'Security review' },
    { id: 'docs', kind: 'judgement', name: 'Only touches docs', to: 'Light docs review' },
    { id: 'unsure', kind: 'unsure', name: 'Not sure', to: 'Ask a person' },
    { id: 'always', kind: 'always', name: 'Anything else', to: 'Full review' },
  ];
  const list = $('.paths', w), log = $('[data-log]', w), calls = $('[data-calls]', w);
  list.innerHTML = PATHS.map((a, i) =>
    `<li><span class="n">${i + 1}</span><span><span class="name">${a.name}</span> <span class="to">→ ${a.to}</span>${a.kind === 'judgement' ? ' <span class="kind">asks Jev</span>' : ''}</span><span class="st"></span></li>`).join('');
  const lis = $$('li', list);
  $('[data-sc]', w).innerHTML = D.gate.map((g, i) => `<button data-i="${i}">${esc(g.label)}</button>`).join('');

  function trace(answers) {
    const steps = []; let asked = 0;
    const push = (i, st, msg, p) => steps.push({ i, st, msg, p, calls: asked });
    for (const [i, a] of PATHS.entries()) {
      if (a.kind === 'unsure') { push(i, 'skip', 'Only used when Jev is unsure. Skipped.'); continue; }
      if (a.kind === 'always') { push(i, 'take', 'Nothing else applied: full review.'); return steps; }
      const pre = asked ? '' : 'One call asks Jev all three questions. ';
      asked = 1;
      const p = answers[a.id], v = band(p);
      if (v === 'take') { push(i, 'take', `${pre}${f2(p)}: a confident yes.`, p); return steps; }
      if (v === 'skip') { push(i, 'skip', `${pre}${f2(p)}: a confident no. Next.`, p); continue; }
      push(i, 'unsure', `${pre}${f2(p)}: unsure, so the gate stops instead of guessing.`, p);
      push(PATHS.findIndex(x => x.kind === 'unsure'), 'take', 'Handed to a person.');
      return steps;
    }
    return steps;
  }

  let steps = [], at = 0;
  const paint = () => {
    lis.forEach(li => { li.className = ''; $('.st', li).innerHTML = ''; });
    steps.slice(0, at).forEach(s => {
      const li = lis[s.i];
      li.classList.add('seen');
      if (s.st === 'take') li.classList.add('won');
      $('.st', li).innerHTML = s.p !== undefined ? chip(s.p)
        : s.st === 'take' ? '<span class="chip take">takes it</span>' : '<span class="chip skip">no</span>';
    });
    const last = steps[at - 1];
    if (last) lis[last.i].classList.add('cur');
    log.textContent = last ? last.msg : 'Press Step to check each path in order.';
    calls.textContent = `Jev calls: ${last ? last.calls : 0}`;
    $('[data-step]', w).disabled = at >= steps.length;
  };
  seg($('[data-sc]', w), b => {
    const g = D.gate[+b.dataset.i];
    $('[data-state]', w).textContent = g.title;
    steps = trace(g.answers); at = 0; paint();
  }).pick($('[data-sc] button', w));
  $('[data-step]', w).addEventListener('click', () => { at = Math.min(at + 1, steps.length); paint(); });
  $('[data-run]', w).addEventListener('click', () => { at = steps.length; paint(); });
  $('[data-reset]', w).addEventListener('click', () => { at = 0; paint(); });
})();

// Fill each slider's track up to its thumb
for (const r of $$('input[type=range]')) { r.addEventListener('input', () => fillOf(r)); fillOf(r); }
