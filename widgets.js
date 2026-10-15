// Little widgets for the tutorial. Every Jev number here is mocked: nothing calls an API.
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const f2 = p => p.toFixed(2);
const clamp = (x, lo = 0.03, hi = 0.97) => Math.min(hi, Math.max(lo, x));
const band = (p, yes = 0.8, no = 0.35) => (p >= yes ? 'take' : p >= no ? 'unsure' : 'skip');
const chip = (p, cls = band(p)) => `<span class="chip ${cls}">${f2(p)}</span>`;
const meter = p => `<span class="bar" style="--w:${Math.round(p * 100)}%"></span>`;
const row = (label, p) => `<div class="wrow"><span class="lab">${label}</span><span>${meter(p)}${chip(p)}</span></div>`;

function seg(root, onPick) {
  const btns = $$('button', root);
  const pick = b => { btns.forEach(x => x.setAttribute('aria-pressed', x === b)); onPick(b); };
  btns.forEach(b => b.addEventListener('click', () => pick(b)));
  return btns;
}

// Substring rule vs a typed answer
(() => {
  const w = $('#w-parse'); if (!w) return;
  const input = $('input', w), rule = $('[data-rule]', w), jev = $('[data-jev]', w);
  const STRONG = /\b(ready|green|merged?|works|done|fixed|lgtm|ship(ped)?)\b/g;
  const WEAK = /\b(pass(ed|es)?|yes|ok(ay)?)\b/g;
  const NEG = /\b(not|never|still|crash\w*|fail\w*|wrong|broken|regress\w*|blocked)\b|n['’]t\b/g;
  const FLIP = /\bnot\s+(pass|ready|work|done)/;
  const n = (s, re) => (s.match(re) || []).length;
  const mock = t => {
    const s = t.toLowerCase();
    return clamp(0.5 + 0.3 * n(s, STRONG) + 0.2 * n(s, WEAK) - 0.45 * n(s, NEG) - (FLIP.test(s) ? 0.3 : 0));
  };
  const say = { take: 'ready to move on', unsure: 'not sure, ask a person', skip: 'not done' };
  const render = () => {
    const t = input.value, u = t.toUpperCase().trim();
    const hit = u.includes('PASS') || u.startsWith('YES');
    rule.innerHTML = `<span class="chip ${hit ? 'take' : 'skip'}">${hit ? 'counts as a pass' : 'counts as a fail'}</span>`;
    const p = t.trim() ? mock(t) : 0.5;
    jev.innerHTML = `${meter(p)}${chip(p)}<span class="dim">${say[band(p)]}</span>`;
  };
  const btns = seg($('.chips', w), b => { input.value = b.textContent; render(); });
  input.addEventListener('input', () => { btns.forEach(x => x.setAttribute('aria-pressed', false)); render(); });
  render();
})();

// Confidence vs the winning probability
(() => {
  const w = $('#w-conf'); if (!w) return;
  const sliders = $$('input[type=range]', w), outs = $$('[data-opt]', w);
  const names = sliders.map(s => s.getAttribute('aria-label'));
  const render = () => {
    const raw = sliders.map(s => Math.max(+s.value, 0.1));
    const sum = raw.reduce((a, b) => a + b, 0), p = raw.map(x => x / sum);
    const H = -p.reduce((a, x) => a + x * Math.log(x), 0);
    const conf = 1 - H / Math.log(p.length);
    const top = p.indexOf(Math.max(...p));
    outs.forEach((o, i) => { o.textContent = f2(p[i]); });
    $('[data-conf]', w).textContent = f2(conf);
    $('[data-top]', w).textContent = `${names[top]} wins with ${f2(p[top])}`;
  };
  sliders.forEach(s => s.addEventListener('input', render));
  $('[data-reset]', w).addEventListener('click', () => { [16, 84, 0].forEach((v, i) => { sliders[i].value = v; sliders[i].dispatchEvent(new Event('input')); }); });
  render();
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
      p >= yes ? ['go this way', 'var(--accent)', 'A confident yes, so the gate takes this path.']
      : p >= no ? ['not sure', 'var(--unsure-ink)', 'Jev isn’t sure, so the gate stops and asks a person.']
      : ['skip', 'var(--muted)', 'A confident no, so the gate checks the next path.'];
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

// Fan-out: questions in sequence vs in one call
(() => {
  const w = $('#w-fan'); if (!w) return;
  const r = $('input', w), AGENT = 6.5, MAX = 10 * AGENT;
  const render = () => {
    const k = +r.value, agent = k * AGENT, jev = 0.18 + 0.006 * k;
    $('[data-n]', w).textContent = `${k} question${k > 1 ? 's' : ''} about one PR`;
    $('[data-agent]', w).innerHTML = Array.from({ length: k }, () => `<i style="width:${(AGENT / MAX) * 100}%"></i>`).join('');
    $('[data-jev]', w).innerHTML = `<i class="one" style="width:${(jev / MAX) * 100}%"></i>`;
    $('[data-at]', w).textContent = `${agent.toFixed(1)} s`;
    $('[data-jt]', w).textContent = `${jev.toFixed(2)} s`;
  };
  r.addEventListener('input', render);
  render();
})();

// One multiple-choice question vs a yes/no question for each
(() => {
  const w = $('#w-split'); if (!w) return;
  const boxes = $$('input[type=checkbox]', w), labels = ['touches auth', 'has no tests'];
  const render = () => {
    const t = boxes.map(b => b.checked), k = t.filter(Boolean).length;
    const raw = [...t.map(x => (x ? 0.94 / Math.max(k, 1) : 0.03)), k ? 0.03 : 0.94];
    const s = raw.reduce((a, b) => a + b, 0), cp = raw.map(x => x / s);
    $('[data-choice]', w).innerHTML = [...labels, 'neither'].map((l, i) => row(l, cp[i])).join('');
    $('[data-noul]', w).innerHTML = labels.map((l, i) => row(l, t[i] ? 0.95 : 0.04)).join('');
    $('[data-note]', w).textContent =
      k === 2 ? 'Both are true, so the choice has to split its belief, and each lands around 0.48, which reads as unsure. The yes/no questions judge each one on its own, so both come back as a confident yes.'
      : k === 1 ? 'With only one true, the two approaches agree. The trouble starts when more than one is true.'
      : 'With neither true, the two approaches agree. Tick both boxes to see where they come apart.';
  };
  boxes.forEach(b => b.addEventListener('change', render));
  render();
})();

// Step through a gate
(() => {
  const w = $('#w-gate'); if (!w) return;
  const PATHS = [
    { id: 'fix', kind: 'rule', name: 'The review failed', to: 'Send back to fix' },
    { id: 'catalog', kind: 'judgement', name: 'Only adds a catalog entry', to: 'Quick catalog checks' },
    { id: 'security', kind: 'judgement', name: 'Touches auth or secrets', to: 'Security review' },
    { id: 'unsure', kind: 'unsure', name: 'Not sure', to: 'Ask a person' },
    { id: 'always', kind: 'always', name: 'Anything else', to: 'Full review' },
  ];
  const SC = {
    catalog: { verdict: 'PASS', summary: 'Adds a linear-sync entry to the integrations catalog', nouls: { catalog: 0.97, security: 0.03 } },
    token: { verdict: 'PASS', summary: 'Moves OAuth token refresh into a shared helper', nouls: { catalog: 0.02, security: 0.58 } },
    csrf: { verdict: 'FAIL', summary: 'Removed the CSRF check on /logout', nouls: { catalog: 0.01, security: 0.96 } },
    typo: { verdict: 'PASS', summary: 'Fixes a typo in a log message', nouls: { catalog: 0.04, security: 0.05 } },
  };
  const list = $('.arms', w), log = $('[data-log]', w), calls = $('[data-calls]', w);
  list.innerHTML = PATHS.map((a, i) =>
    `<li><span class="n">${i + 1}</span><span><span class="name">${a.name}</span> <span class="to">→ ${a.to}</span>${a.kind === 'judgement' ? ' <span class="kind">asks Jev</span>' : ''}</span><span class="st"></span></li>`).join('');
  const lis = $$('li', list);

  function trace(sc) {
    const steps = []; let asked = 0;
    const push = (i, st, msg, p) => steps.push({ i, st, msg, p, calls: asked });
    for (const [i, a] of PATHS.entries()) {
      if (a.kind === 'rule') {
        if (sc.verdict === 'FAIL') { push(i, 'take', 'The review failed, so the change goes back to be fixed. The gate never needs to ask Jev.'); return steps; }
        push(i, 'skip', 'The review passed, so this doesn’t apply. On to the next path.'); continue;
      }
      if (a.kind === 'unsure') { push(i, 'skip', '“Not sure” only applies when Jev comes back unsure, so the gate passes over it.'); continue; }
      if (a.kind === 'always') { push(i, 'take', 'Nothing else applied, so it gets the full review.'); return steps; }
      const pre = asked ? '' : 'This is the first question for Jev, so the gate asks both of its questions in one call. ';
      asked = 1;
      const p = sc.nouls[a.id], v = band(p);
      if (v === 'take') { push(i, 'take', `${pre}This one came back ${f2(p)}, a confident yes.`, p); return steps; }
      if (v === 'skip') { push(i, 'skip', `${pre}This one came back ${f2(p)}, a confident no, so the gate moves on.`, p); continue; }
      push(i, 'unsure', `${pre}This one came back ${f2(p)}, in the unsure band. The gate stops here rather than guess.`, p);
      push(PATHS.findIndex(x => x.kind === 'unsure'), 'take', 'It goes to “Not sure”, and the run waits for a person.');
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
  const load = k => {
    const sc = SC[k];
    $('[data-state]', w).innerHTML = `${sc.summary} · review <strong>${sc.verdict === 'PASS' ? 'passed' : 'failed'}</strong>`;
    steps = trace(sc); at = 0; paint();
  };
  seg($('[data-sc]', w), b => load(b.dataset.k));
  $('[data-step]', w).addEventListener('click', () => { at = Math.min(at + 1, steps.length); paint(); });
  $('[data-run]', w).addEventListener('click', () => { at = steps.length; paint(); });
  $('[data-reset]', w).addEventListener('click', () => { at = 0; paint(); });
  load('catalog');
})();

// Fill each slider's track up to its thumb
for (const r of $$('input[type=range]')) {
  const fill = () => r.style.setProperty('--fill', `${((r.value - r.min) / (r.max - r.min)) * 100}%`);
  r.addEventListener('input', fill); fill();
}
