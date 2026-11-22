const tour = document.querySelector('.tour');
const slides = Array.from(document.querySelectorAll('.slide'));
const previous = document.querySelector('#previous');
const next = document.querySelector('#next');
const status = document.querySelector('.note');
const hint = status.textContent;
let page = 0;
let pending = false;
let done = false;

function readPage() {
  const n = Number(location.hash.slice(1));
  return Number.isInteger(n) && n >= 1 && n <= slides.length ? n - 1 : 0;
}
function display(n) {
  page = Math.max(0, Math.min(n, slides.length - 1));
  tour.dataset.step = page + 1;
  slides.forEach((slide, i) => {slide.hidden = i !== page;});
  document.querySelectorAll('.track i').forEach((mark, i) => mark.classList.toggle('on', i <= page));
  document.querySelector('.count').textContent = (page + 1) + ' / ' + slides.length;
  previous.disabled = page === 0 || pending || done;
  next.disabled = pending || done;
  next.textContent = page === slides.length - 1 ? next.dataset.finish : next.dataset.next;
  document.querySelectorAll('nav a').forEach(link => {link.hash = String(page + 1);});
  if (!pending && !done) status.textContent = hint;
}
function move(n) {
  if (pending || done) return;
  display(n);
  history.replaceState(null, '', '#' + (page + 1));
}
async function forward() {
  if (pending || done) return;
  if (page < slides.length - 1) {move(page + 1); return;}
  if (location.protocol === 'file:') {
    location.href = 'nkc-translater://open';
    status.textContent = next.dataset.local;
    return;
  }
  pending = true;
  display(page);
  try {
    const response = await fetch('../finish', {method:'POST', headers:{'X-Tour-Action':'finish'}});
    if (!response.ok) throw Error('Launch unavailable');
    done = true;
    status.textContent = next.dataset.done;
  } catch {
    status.textContent = next.dataset.error;
  } finally {
    pending = false;
    previous.disabled = done;
    next.disabled = done;
  }
}
previous.addEventListener('click', () => move(page - 1));
next.addEventListener('click', forward);
window.addEventListener('hashchange', () => display(readPage()));
window.addEventListener('keydown', event => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.isComposing ||
      ['Tab','Escape','Shift','Control','Meta','Alt','CapsLock','ContextMenu','Dead','Process','Unidentified'].includes(event.key)) return;
  if (event.repeat) { event.preventDefault(); return; }
  if (event.key === 'Enter' && event.target.closest('a,button')) return;
  if (event.key === ' ' && event.target.closest('button')) return;
  event.preventDefault();
  if (['ArrowLeft','ArrowUp','PageUp','Backspace'].includes(event.key)) move(page - 1);
  else forward();
});
function mountainLayer(group) {
  const outline = group.querySelector('polygon').points;
  const spine = group.querySelector('polyline').points;
  const vertices = Array.from(outline).slice(0, -2).map(point => ({
    x: point.x, y: point.y, amplitude: 6 + Math.random() * 9,
    rate: .45 + Math.random() * .65, phase: Math.random() * Math.PI * 2
  }));
  const anchors = Array.from(spine, point => {
    let i = 0;
    while (i < vertices.length - 2 && vertices[i + 1].x < point.x) i++;
    const fraction = (point.x - vertices[i].x) / (vertices[i + 1].x - vertices[i].x);
    return {y: point.y, i, fraction};
  });
  return time => {
    const shifts = vertices.map(v => v.amplitude * Math.sin(v.phase + time * v.rate));
    vertices.forEach((v, i) => { outline.getItem(i).y = v.y + shifts[i]; });
    anchors.forEach(({y, i, fraction}, k) => {
      spine.getItem(k).y = y + shifts[i] + fraction * (shifts[i + 1] - shifts[i]);
    });
  };
}
const layers = Array.from(document.querySelectorAll('.mountains-front,.mountains-back'), mountainLayer);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
let animation = 0;
let lastFrame = null;
let seconds = 0;
function frame(now) {
  if (lastFrame === null || now - lastFrame >= 32) {
    if (lastFrame !== null) seconds += (now - lastFrame) / 1000;
    layers.forEach(render => render(seconds));
    lastFrame = now;
  }
  animation = requestAnimationFrame(frame);
}
function syncMotion() {
  cancelAnimationFrame(animation);
  lastFrame = null;
  if (!document.hidden && document.hasFocus() && !reducedMotion.matches)
    animation = requestAnimationFrame(frame);
}
reducedMotion.addEventListener('change', syncMotion);
window.addEventListener('focus', syncMotion);
window.addEventListener('blur', syncMotion);
document.addEventListener('visibilitychange', syncMotion);
display(readPage());
syncMotion();

