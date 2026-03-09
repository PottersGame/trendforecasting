/**
 * RUNWAY AI — Fashion Trend Forecasting
 * Main application JavaScript
 *
 * Sections: dashboard | trends | aesthetics | google | colors |
 *           social | news | brands | calendar | ai | forecast | search
 */

'use strict';

// ── Chart defaults ──────────────────────────────────────────────────────────
const PALETTE = [
  '#a855f7','#22d3ee','#ec4899','#3b82f6','#f59e0b',
  '#10b981','#c084fc','#67e8f9','#f9a8d4','#818cf8',
  '#34d399','#fb7185',
];

Chart.defaults.color        = '#9d99b8';
Chart.defaults.borderColor  = '#1e1e30';
Chart.defaults.font.family  = "'Inter', sans-serif";
Chart.defaults.font.size    = 12;

const chartInstances = {};

function destroyChart(id) {
  if (chartInstances[id]) {
    chartInstances[id].destroy();
    delete chartInstances[id];
  }
}

function makeChart(id, config) {
  destroyChart(id);
  const ctx = document.getElementById(id);
  if (!ctx) return null;
  chartInstances[id] = new Chart(ctx, config);
  return chartInstances[id];
}

// ── API key management ───────────────────────────────────────────────────────
const API_KEY_STORAGE = 'runway_api_key';

function getApiKey() {
  return localStorage.getItem(API_KEY_STORAGE) || '';
}

function setApiKey(key) {
  if (key) {
    localStorage.setItem(API_KEY_STORAGE, key);
  } else {
    localStorage.removeItem(API_KEY_STORAGE);
  }
}

function openKeyModal(message) {
  const modal   = document.getElementById('apiKeyModal');
  const msgEl   = document.getElementById('apiKeyMessage');
  const inputEl = document.getElementById('apiKeyInput');
  if (!modal) return;
  if (message && msgEl) msgEl.textContent = message;
  if (inputEl) inputEl.value = getApiKey();
  modal.classList.remove('hidden');
}

function closeKeyModal() {
  const modal = document.getElementById('apiKeyModal');
  if (modal) modal.classList.add('hidden');
}

document.getElementById('apiKeySaveBtn')?.addEventListener('click', () => {
  const inputEl = document.getElementById('apiKeyInput');
  const key = inputEl ? inputEl.value.trim() : '';
  setApiKey(key);
  closeKeyModal();
  // Reload current section so protected content now loads.
  Object.keys(sectionLoaded).forEach(k => sectionLoaded[k] = false);
  showSection(currentSection());
});

document.getElementById('apiKeyCancelBtn')?.addEventListener('click', closeKeyModal);

document.getElementById('apiKeyBtn')?.addEventListener('click', () => {
  openKeyModal('Enter your API key (set via the APP_API_KEY env var on the server).');
});

// ── API helper ──────────────────────────────────────────────────────────────
async function api(path, opts = {}) {
  try {
    const key = getApiKey();
    if (key) {
      const headers = new Headers(opts.headers || {});
      headers.set('Authorization', 'Bearer ' + key);
      opts = { ...opts, headers };
    }
    const res = await fetch('/api' + path, opts);
    if (res.status === 401) {
      openKeyModal('Your API key is missing or incorrect. Enter it below to access AI features.');
      return null;
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    console.warn('API error:', path, e.message);
    return null;
  }
}

// ── Navigation ──────────────────────────────────────────────────────────────
const sections = document.querySelectorAll('.section');
const navItems = document.querySelectorAll('.nav-item');

function showSection(id) {
  sections.forEach(s => s.classList.toggle('active', s.id === id));
  navItems.forEach(n => n.classList.toggle('active', n.dataset.section === id));
  // Lazy-load section data
  loaders[id] && loaders[id]();
}

navItems.forEach(n => n.addEventListener('click', e => {
  e.preventDefault();
  showSection(n.dataset.section);
}));

document.getElementById('menuToggle')?.addEventListener('click', () => {
  document.getElementById('sidebar').classList.toggle('open');
});

// ── Loading overlay ──────────────────────────────────────────────────────────
function hideLoader() {
  document.getElementById('loadingOverlay').classList.add('hidden');
}

// ── Refresh ──────────────────────────────────────────────────────────────────
document.getElementById('refreshBtn')?.addEventListener('click', () => {
  Object.keys(sectionLoaded).forEach(k => sectionLoaded[k] = false);
  showSection(currentSection());
});

function currentSection() {
  return [...sections].find(s => s.classList.contains('active'))?.id || 'dashboard';
}

// Track which sections have been loaded
const sectionLoaded = {};

function once(key, fn) {
  if (sectionLoaded[key]) return;
  sectionLoaded[key] = true;
  fn();
}

// ── Utils ────────────────────────────────────────────────────────────────────
function fmt(n) { return typeof n === 'number' ? n.toLocaleString() : (n || '—'); }
function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : ''; }
function clr(i) { return PALETTE[i % PALETTE.length]; }

function momentumBadge(m) {
  const map = { rising: '↑ Rising', stable: '→ Stable', falling: '↓ Falling' };
  return `<span class="momentum-badge momentum-${m}">${map[m] || m}</span>`;
}

function scoreBar(score) {
  return `
    <div class="trend-bar-wrap">
      <div class="trend-bar-bg">
        <div class="trend-bar-fill" style="width:${score}%"></div>
      </div>
      <div class="trend-score-label">${score}/100</div>
    </div>`;
}

// ── DASHBOARD ────────────────────────────────────────────────────────────────
async function loadDashboard() {
  once('dashboard', async () => {
    const data = await api('/dashboard');
    if (!data) { hideLoader(); return; }

    // Season badge
    document.getElementById('seasonBadge').textContent = data.season + ' ' + new Date().getFullYear();

    // KPIs
    const top = data.top_trends?.[0];
    document.getElementById('kpiTopTrend').textContent    = top?.name || '—';
    document.getElementById('kpiTopAesthetic').textContent = data.top_trends?.[1]?.name || '—';
    document.getElementById('kpiRedditPosts').textContent  = fmt(data.db_stats?.total_reddit || data.top_reddit?.length || 0);
    document.getElementById('kpiNewsArticles').textContent = fmt(data.db_stats?.total_news   || data.top_news?.length  || 0);

    // AI overview
    document.getElementById('aiOverviewText').textContent =
      data.ai_overview || 'No AI analysis available (configure GROQ_API_KEY, OPENAI_API_KEY, or run Ollama locally).';

    // Trend momentum bar chart
    if (data.top_trends?.length) {
      const top10 = data.top_trends.slice(0, 10);
      makeChart('trendMomentumChart', {
        type: 'bar',
        data: {
          labels: top10.map(t => t.name),
          datasets: [{
            label: 'Trend Score',
            data:  top10.map(t => t.score),
            backgroundColor: top10.map((t, i) =>
              t.momentum === 'rising'  ? 'rgba(76,175,80,.75)'  :
              t.momentum === 'falling' ? 'rgba(201,67,94,.75)'  :
              `${clr(i)}bb`
            ),
            borderColor: top10.map((t, i) =>
              t.momentum === 'rising'  ? '#4caf50' :
              t.momentum === 'falling' ? '#c9435e' : clr(i)
            ),
            borderWidth: 1,
            borderRadius: 6,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: true,
          indexAxis: 'y',
          plugins: { legend: { display: false } },
          scales: {
            x: { beginAtZero: true, max: 100, grid: { color: '#2a2a30' } },
            y: { grid: { display: false } },
          },
        },
      });
    }

    // Category donut
    if (data.top_trends?.length) {
      const cats = {};
      data.top_trends.forEach(t =>
        (t.categories || []).forEach(c => cats[c] = (cats[c] || 0) + (t.score || 1))
      );
      const labels = Object.keys(cats);
      const values = labels.map(l => cats[l]);
      makeChart('categoryDonutChart', {
        type: 'doughnut',
        data: {
          labels,
          datasets: [{ data: values, backgroundColor: labels.map((_, i) => clr(i)), borderWidth: 0 }],
        },
        options: {
          responsive: true, maintainAspectRatio: true,
          plugins: {
            legend: { position: 'right', labels: { boxWidth: 12, padding: 10 } },
          },
          cutout: '65%',
        },
      });
    }

    // Subreddit bar chart
    if (data.activity?.length) {
      const subs = data.activity.slice(0, 8);
      makeChart('subredditChart', {
        type: 'bar',
        data: {
          labels: subs.map(s => s.label),
          datasets: [{
            label: 'Total Score',
            data:  subs.map(s => s.total_score),
            backgroundColor: subs.map((_, i) => `${clr(i)}bb`),
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { maxRotation: 30 } },
            y: { grid: { color: '#2a2a30' } },
          },
        },
      });
    }

    // Brand buzz bar chart
    if (data.top_brands?.length) {
      const brands = data.top_brands.filter(b => b.mentions > 0).slice(0, 10);
      makeChart('brandBuzzChart', {
        type: 'bar',
        data: {
          labels: brands.map(b => b.brand),
          datasets: [{
            label: 'Mentions',
            data:  brands.map(b => b.mentions),
            backgroundColor: brands.map((_, i) => `${clr(i)}bb`),
            borderRadius: 4,
          }],
        },
        options: {
          responsive: true, maintainAspectRatio: true,
          indexAxis: 'y',
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: '#2a2a30' } },
            y: { grid: { display: false } },
          },
        },
      });
    }

    // Top posts grid
    const grid = document.getElementById('topPostsGrid');
    if (grid) {
      const posts = [...(data.top_reddit || []), ...(data.top_news || [])].slice(0, 12);
      grid.innerHTML = posts.map(p => `
        <div class="post-card" onclick="window.open('${p.permalink || p.url}','_blank')">
          <div class="post-source">${p.source || 'Reddit'}</div>
          <div class="post-title">${p.title}</div>
          <div class="post-meta">
            ${p.score ? `<span class="post-score">↑ ${fmt(p.score)}</span>` : ''}
            ${p.comments ? `<span>💬 ${fmt(p.comments)}</span>` : ''}
            ${p.category ? `<span class="post-category">${p.category}</span>` : ''}
          </div>
        </div>`).join('');
    }

    hideLoader();
  });
}

// ── TREND RADAR ──────────────────────────────────────────────────────────────
async function loadTrends() {
  once('trends', async () => {
    const trends = await api('/trends');
    if (!trends) return;
    renderTrendList(trends, 'all');

    // Filter buttons
    document.querySelectorAll('.trend-filter-row .filter-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('.trend-filter-row .filter-btn')
          .forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        renderTrendList(trends, btn.dataset.cat);
      });
    });

    // Populate AI dropdown
    const sel = document.getElementById('aiTrendSelect');
    if (sel && !sel.options.length) {
      trends.forEach(t => {
        const o = document.createElement('option');
        o.value = t.name; o.textContent = t.name;
        sel.appendChild(o);
      });
    }
  });
}

function renderTrendList(trends, cat) {
  const el = document.getElementById('trendList');
  if (!el) return;
  const filtered = cat === 'all' ? trends :
    trends.filter(t => (t.categories || []).includes(cat));
  el.innerHTML = filtered.map((t, i) => `
    <div class="trend-item">
      <div class="trend-rank ${i < 3 ? 'top3' : ''}">${String(i + 1).padStart(2, '0')}</div>
      <div class="trend-info">
        <div class="trend-name">${t.name}</div>
        <div class="trend-cats">
          ${(t.categories || []).map(c => `<span class="trend-cat">${c}</span>`).join('')}
        </div>
      </div>
      ${scoreBar(t.score)}
      ${momentumBadge(t.momentum || 'stable')}
    </div>`).join('');
}

// ── AESTHETICS ───────────────────────────────────────────────────────────────
async function loadAesthetics() {
  once('aesthetics', async () => {
    // Parallel fetch
    const [viral, style, sustainable, luxury] = await Promise.all([
      api('/aesthetics/viral_aesthetics'),
      api('/aesthetics/style_movements'),
      api('/aesthetics/sustainable'),
      api('/aesthetics/luxury'),
    ]);

    const groupScores = await api('/aesthetics');

    function renderAestheticsChart(id, data) {
      if (!data || !data.dates || !data.dates.length) return;
      const datasets = Object.entries(data.data || {}).map(([kw, vals], i) => ({
        label: kw,
        data: vals,
        borderColor: clr(i),
        backgroundColor: 'transparent',
        tension: 0.4,
        borderWidth: 2,
        pointRadius: 0,
        pointHoverRadius: 4,
      }));
      makeChart(id, {
        type: 'line',
        data: { labels: data.dates, datasets },
        options: {
          responsive: true, maintainAspectRatio: true,
          plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 8 } } },
          scales: {
            x: {
              ticks: { maxTicksLimit: 8, maxRotation: 0 },
              grid: { color: '#2a2a30' },
            },
            y: { beginAtZero: true, max: 100, grid: { color: '#2a2a30' } },
          },
        },
      });
    }

    renderAestheticsChart('aestheticsTimeChart',  viral);
    renderAestheticsChart('styleMovementsChart',  style);
    renderAestheticsChart('sustainableChart',      sustainable);
    renderAestheticsChart('luxuryChart',           luxury);

    // Aesthetic score cards
    if (groupScores) {
      const el = document.getElementById('aestheticCards');
      if (el) {
        const labels = {
          viral_aesthetics: 'Viral Aesthetics',
          style_movements:  'Style Movements',
          sustainable:      'Sustainable Fashion',
          streetwear:       'Streetwear',
          luxury:           'Luxury',
          seasonal:         'Seasonal',
          color_trends:     'Color Trends',
        };
        el.innerHTML = Object.entries(groupScores).map(([k, v]) => `
          <div class="aesthetic-card">
            <div class="aesthetic-name">${labels[k] || cap(k)}</div>
            <div class="aesthetic-score-num">${v || 0}</div>
            <div class="aesthetic-label">avg interest score</div>
          </div>`).join('');
      }
    }
  });
}

// ── SEARCH PULSE (Google Trends) ─────────────────────────────────────────────
let searchChartData = null;

async function loadGoogleTrends() {
  once('google', async () => {
    const data = await api('/google-trends?group=viral_aesthetics');
    renderSearchChart(data, 'Viral Aesthetics — Interest Over Time');
  });
}

async function renderSearchChart(data, title) {
  if (!data || !data.dates?.length) return;
  document.getElementById('searchChartTitle').textContent = title;
  const datasets = Object.entries(data.data || {}).map(([kw, vals], i) => ({
    label: kw,
    data: vals,
    borderColor: clr(i),
    backgroundColor: clr(i) + '22',
    fill: true,
    tension: 0.4,
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 5,
  }));
  makeChart('searchTrendsChart', {
    type: 'line',
    data: { labels: data.dates, datasets },
    options: {
      responsive: true, maintainAspectRatio: true,
      plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 8 } } },
      scales: {
        x: { ticks: { maxTicksLimit: 10, maxRotation: 0 }, grid: { color: '#2a2a30' } },
        y: { beginAtZero: true, max: 100, grid: { color: '#2a2a30' } },
      },
    },
  });
}

document.getElementById('searchBtn')?.addEventListener('click', async () => {
  const val = document.getElementById('searchInput').value.trim();
  if (!val) return;
  const kws = val.split(',').map(s => s.trim()).filter(Boolean).slice(0, 5);
  const data = await api(`/google-trends?keywords=${encodeURIComponent(kws.join(','))}`);
  renderSearchChart(data, `Interest Over Time: ${kws.join(', ')}`);

  // Related queries for the first keyword
  const related = await api(`/related-queries?keyword=${encodeURIComponent(kws[0])}`);
  if (related) {
    document.getElementById('risingQueries').innerHTML =
      (related.rising || []).map(q => `
        <div class="query-item">
          <span>${q.query}</span>
          <span class="query-value">+${q.value}%</span>
        </div>`).join('') || '<p style="color:#6b6560;font-size:13px;">No data available</p>';
    document.getElementById('topQueries').innerHTML =
      (related.top || []).map(q => `
        <div class="query-item">
          <span>${q.query}</span>
          <span class="query-value">${q.value}</span>
        </div>`).join('') || '<p style="color:#6b6560;font-size:13px;">No data available</p>';
  }
});

// ── COLORS ───────────────────────────────────────────────────────────────────
async function loadColors() {
  once('colors', async () => {
    const colors = await api('/colors');
    if (!colors) return;

    // Swatches
    const palette = document.getElementById('colorPalette');
    if (palette) {
      palette.innerHTML = colors.map(c => `
        <div class="color-swatch">
          <div class="swatch-color" style="background:${c.hex}"></div>
          <div class="swatch-info">
            <div class="swatch-name">${c.name}</div>
            <div class="swatch-hex">${c.hex}</div>
            <div class="swatch-season">${c.season}</div>
          </div>
        </div>`).join('');
    }

    // Bar chart
    makeChart('colorBarChart', {
      type: 'bar',
      data: {
        labels: colors.map(c => c.name),
        datasets: [{
          label: 'Popularity Score',
          data: colors.map(c => c.score),
          backgroundColor: colors.map(c => c.hex + 'cc'),
          borderColor: colors.map(c => c.hex),
          borderWidth: 1,
          borderRadius: 6,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 30 } },
          y: { beginAtZero: true, max: 100, grid: { color: '#2a2a30' } },
        },
      },
    });
  });
}

// ── SOCIAL BUZZ ───────────────────────────────────────────────────────────────
async function loadSocial() {
  once('social', async () => {
    const [activity, keywords, posts] = await Promise.all([
      api('/reddit/activity'),
      api('/reddit/keywords'),
      api('/reddit'),
    ]);

    // Community chart
    if (activity?.length) {
      const top = activity.slice(0, 10);
      makeChart('communityChart', {
        type: 'bar',
        data: {
          labels: top.map(s => s.label),
          datasets: [
            {
              label: 'Total Score',
              data:  top.map(s => s.total_score),
              backgroundColor: top.map((_, i) => `${clr(i)}bb`),
              borderRadius: 4,
            },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: true,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { display: false }, ticks: { maxRotation: 30 } },
            y: { grid: { color: '#2a2a30' } },
          },
        },
      });
    }

    // Word cloud
    if (keywords?.length) renderWordCloud('wordCloud', keywords);

    // Post grid
    renderRedditPosts(posts || [], '');

    // Category tabs
    document.querySelectorAll('#redditCategoryTabs .tab-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        document.querySelectorAll('#redditCategoryTabs .tab-btn')
          .forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const cat = btn.dataset.cat;
        const data = cat
          ? await api(`/reddit?category=${cat}`)
          : await api('/reddit');
        renderRedditPosts(data || [], cat);
      });
    });
  });
}

function renderRedditPosts(posts, cat) {
  const grid = document.getElementById('redditPostGrid');
  if (!grid) return;
  const filtered = cat ? posts.filter(p => p.category === cat) : posts;
  grid.innerHTML = filtered.slice(0, 12).map(p => `
    <div class="post-card" onclick="window.open('${p.permalink}','_blank')">
      <div class="post-source">r/${p.subreddit}</div>
      <div class="post-title">${p.title}</div>
      <div class="post-meta">
        <span class="post-score">↑ ${fmt(p.score)}</span>
        <span>💬 ${fmt(p.comments)}</span>
        ${p.category ? `<span class="post-category">${p.category}</span>` : ''}
      </div>
    </div>`).join('');
}

function renderWordCloud(containerId, words) {
  const el = document.getElementById(containerId);
  if (!el || !words?.length) return;
  const max = words[0].count || 1;
  const sizes = [11, 13, 15, 17, 20, 23, 26];
  const colors = [...PALETTE, ...PALETTE];
  el.innerHTML = words.slice(0, 40).map((w, i) => {
    const ratio = w.count / max;
    const size  = sizes[Math.min(Math.floor(ratio * sizes.length), sizes.length - 1)];
    const col   = colors[i % colors.length];
    return `<span class="word-tag"
      style="font-size:${size}px;color:${col};border-color:${col}33;background:${col}15">
      ${w.word}
    </span>`;
  }).join('');
}

// ── EDITORIAL NEWS ────────────────────────────────────────────────────────────
async function loadNews() {
  once('news', async () => {
    const articles = await api('/news');
    renderNewsGrid(articles || [], '');

    document.querySelectorAll('.news-filter-row .filter-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        document.querySelectorAll('.news-filter-row .filter-btn')
          .forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const tag = btn.dataset.tag;
        const data = tag ? await api(`/news/${tag}`) : await api('/news');
        renderNewsGrid(data || [], tag);
      });
    });
  });
}

function renderNewsGrid(articles, tag) {
  const grid = document.getElementById('newsGrid');
  if (!grid) return;
  const filtered = tag
    ? articles.filter(a => (a.tags || []).includes(tag))
    : articles;
  grid.innerHTML = filtered.slice(0, 24).map(a => `
    <a href="${a.url}" target="_blank" class="news-card">
      ${a.image
        ? `<img class="news-card-img" src="${a.image}" alt="" loading="lazy" onerror="this.style.display='none'">`
        : `<div class="news-card-img-placeholder">✦</div>`}
      <div class="news-card-body">
        <div class="news-source">${a.source}</div>
        <h3 class="news-headline">${a.title}</h3>
        ${a.description ? `<p class="news-desc">${a.description}</p>` : ''}
        <div class="news-tags">
          ${(a.tags || []).map(t => `<span class="news-tag">${t}</span>`).join('')}
        </div>
      </div>
    </a>`).join('');
}

// ── BRANDS ────────────────────────────────────────────────────────────────────
async function loadBrands() {
  once('brands', async () => {
    const brands = await api('/brands');
    if (!brands) return;

    const withMentions = brands.filter(b => b.mentions > 0);

    // Leaderboard chart
    const top12 = withMentions.slice(0, 12);
    makeChart('brandLeaderboardChart', {
      type: 'bar',
      data: {
        labels: top12.map(b => b.brand),
        datasets: [{
          label: 'Mentions',
          data:  top12.map(b => b.mentions),
          backgroundColor: top12.map((_, i) => `${clr(i)}cc`),
          borderRadius: 6,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        indexAxis: 'y',
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: '#2a2a30' } },
          y: { grid: { display: false } },
        },
      },
    });

    // Luxury vs fast-fashion donut
    const luxury     = ['Gucci','Louis Vuitton','Prada','Chanel','Hermès','Balenciaga','Loewe','Bottega Veneta','Jacquemus'];
    const fastFashion = ['Zara','H&M','Shein','ASOS','Uniqlo'];
    const streetwear  = ['Nike','Adidas','Supreme','Off-White','Stone Island','Carhartt','New Balance'];

    function sumBrand(list) {
      return list.reduce((acc, name) => {
        const b = brands.find(x => x.brand === name);
        return acc + (b ? b.mentions : 0);
      }, 0);
    }

    makeChart('brandSegmentChart', {
      type: 'doughnut',
      data: {
        labels: ['Luxury', 'Fast Fashion', 'Streetwear'],
        datasets: [{
          data: [sumBrand(luxury), sumBrand(fastFashion), sumBrand(streetwear)],
          backgroundColor: ['#d4a574cc','#c9435ecc','#4a6fa5cc'],
          borderWidth: 0,
        }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, padding: 10 } },
        },
        cutout: '60%',
      },
    });

    // Brand cards grid
    const grid = document.getElementById('brandGrid');
    if (grid) {
      grid.innerHTML = withMentions.slice(0, 18).map(b => `
        <div class="brand-card">
          <div class="brand-name">${b.brand}</div>
          <div class="brand-mentions">${b.mentions}</div>
          <div class="brand-mentions-label">mentions</div>
        </div>`).join('');
    }
  });
}

// ── CALENDAR ─────────────────────────────────────────────────────────────────
async function loadCalendar() {
  once('calendar', async () => {
    const events = await api('/calendar');
    const grid   = document.getElementById('calendarGrid');
    if (!grid || !events) return;
    grid.innerHTML = events.map(e => `
      <div class="cal-card">
        <div class="cal-event">${e.event}</div>
        <div class="cal-meta">
          <div><span class="cal-city">📍 ${e.city}</span></div>
          <div>📅 ${e.month}</div>
        </div>
        <span class="cal-type">${e.type}</span>
      </div>`).join('');
  });
}

// ── FORECAST ─────────────────────────────────────────────────────────────────
async function loadForecast() {
  once('forecast', async () => {
    const forecasts = await api('/forecast');
    if (!forecasts?.length) {
      const el = document.getElementById('forecastList');
      if (el) el.innerHTML = '<p class="empty-state">No forecast data yet. Click <strong>Ingest Data</strong> to populate the database.</p>';
      return;
    }

    // Forecast chart — bar chart with current, 7d, 14d, 30d
    const top = forecasts.slice(0, 10);
    makeChart('forecastBarChart', {
      type: 'bar',
      data: {
        labels: top.map(f => f.trend_name),
        datasets: [
          { label: 'Current',   data: top.map(f => f.current_score), backgroundColor: '#d4a57499', borderRadius: 4 },
          { label: '7-day',     data: top.map(f => f.forecast_7d),   backgroundColor: '#c9435e99', borderRadius: 4 },
          { label: '14-day',    data: top.map(f => f.forecast_14d),  backgroundColor: '#4a6fa599', borderRadius: 4 },
          { label: '30-day',    data: top.map(f => f.forecast_30d),  backgroundColor: '#8fae8c99', borderRadius: 4 },
        ],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        plugins: {
          legend: { position: 'top', labels: { boxWidth: 12, padding: 10 } },
        },
        scales: {
          x: { grid: { display: false }, ticks: { maxRotation: 30 } },
          y: { beginAtZero: true, max: 100, grid: { color: '#2a2a30' } },
        },
      },
    });

    // Forecast leaderboard list
    const list = document.getElementById('forecastList');
    if (list) {
      list.innerHTML = forecasts.slice(0, 16).map((f, i) => `
        <div class="trend-item">
          <div class="trend-rank ${i < 3 ? 'top3' : ''}">${String(i+1).padStart(2,'0')}</div>
          <div class="trend-info">
            <div class="trend-name">${f.trend_name}</div>
            <div class="trend-cats">
              <span class="trend-cat">7d: ${f.forecast_7d}</span>
              <span class="trend-cat">14d: ${f.forecast_14d}</span>
              <span class="trend-cat">30d: ${f.forecast_30d}</span>
              <span class="trend-cat">confidence: ${Math.round((f.confidence||0)*100)}%</span>
            </div>
          </div>
          ${scoreBar(f.current_score)}
          ${momentumBadge(f.direction || 'stable')}
        </div>`).join('');
    }
  });
}

// ── SEARCH SECTION ────────────────────────────────────────────────────────────
async function loadSearch() {
  // Nothing to load initially; search is triggered by user input
}

async function runSearch(query) {
  if (!query.trim()) return;
  const resultEl   = document.getElementById('searchResultAnalysis');
  const newsEl     = document.getElementById('searchResultNews');
  const redditEl   = document.getElementById('searchResultReddit');
  const modelEl    = document.getElementById('searchModelUsed');

  if (resultEl) resultEl.textContent = 'Searching and analysing…';

  const data = await api(`/search?q=${encodeURIComponent(query)}`);
  if (!data) {
    if (resultEl) resultEl.textContent = 'Search failed. Please try again.';
    return;
  }

  if (resultEl) resultEl.textContent = data.analysis || 'No analysis available.';
  if (modelEl)  modelEl.textContent  = `Model: ${data.model || 'rule-based'}`;

  if (newsEl) {
    newsEl.innerHTML = (data.news || []).length
      ? data.news.map(a => `
          <div class="query-item" style="cursor:pointer" onclick="window.open('${a.url}','_blank')">
            <span>[${a.source}] ${a.title}</span>
          </div>`).join('')
      : '<p style="color:#6b6560;font-size:12px;padding:8px">No news records found in database</p>';
  }
  if (redditEl) {
    redditEl.innerHTML = (data.reddit || []).length
      ? data.reddit.map(p => `
          <div class="query-item" style="cursor:pointer" onclick="window.open('${p.permalink}','_blank')">
            <span>[r/${p.subreddit} ↑${p.score}] ${p.title}</span>
          </div>`).join('')
      : '<p style="color:#6b6560;font-size:12px;padding:8px">No Reddit records found in database</p>';
  }
}

// ── AI ANALYST ────────────────────────────────────────────────────────────────
async function loadAI() {
  once('ai', async () => {
    const [overview, season, newsAnalysis, trendData, models] = await Promise.all([
      api('/ai/overview'),
      api('/ai/season'),
      api('/ai/news-analysis'),
      api('/trends'),
      api('/ai/models'),
    ]);

    if (overview) {
      document.getElementById('aiOverviewMain').textContent = overview.analysis || '—';
    }
    if (season) {
      document.getElementById('aiSeasonTitle').textContent = season.season + ' ' + new Date().getFullYear() + ' Outlook';
      document.getElementById('aiSeasonText').textContent  = season.analysis || '—';
    }
    if (newsAnalysis) {
      document.getElementById('aiNewsText').textContent = newsAnalysis.analysis || '—';
    }

    // Model availability indicator
    if (models) {
      const indicator = document.getElementById('aiModelIndicator');
      if (indicator) {
        const active = models.groq_enabled   ? 'Groq (llama3-8b)'
                     : models.gemini_enabled  ? 'Gemini (gemini-1.5-flash)'
                     : models.openai_enabled  ? 'OpenAI (gpt-3.5)'
                     : models.ollama_running  ? `Ollama (${models.ollama_model})`
                     : 'Rule-based (no LLM configured)';
        indicator.textContent = `Active model: ${active}`;
      }
    }

    // Populate trend dropdown
    if (trendData?.length) {
      const sel = document.getElementById('aiTrendSelect');
      if (sel && !sel.options.length) {
        trendData.forEach(t => {
          const o = document.createElement('option');
          o.value = t.name; o.textContent = t.name;
          sel.appendChild(o);
        });
      }
    }
  });
}

document.getElementById('aiAnalyseBtn')?.addEventListener('click', async () => {
  const sel  = document.getElementById('aiTrendSelect');
  const name = sel?.value;
  if (!name) return;

  document.getElementById('aiTrendName').textContent = name;
  document.getElementById('aiTrendText').textContent = 'Analysing…';
  document.getElementById('aiStyleTip').textContent  = '';

  const [analysis, tip] = await Promise.all([
    api(`/ai/trend/${encodeURIComponent(name)}`),
    api(`/ai/tip/${encodeURIComponent(name)}`),
  ]);

  document.getElementById('aiTrendText').textContent =
    analysis?.analysis || 'No analysis available.';
  if (tip?.tip) {
    document.getElementById('aiStyleTip').textContent = '💡 Style Tip: ' + tip.tip;
  }

  const modelBadge = document.getElementById('aiTrendModel');
  if (modelBadge) modelBadge.textContent = `Model: ${analysis?.model || 'rule-based'}`;
});

// ── DB INGEST button ──────────────────────────────────────────────────────────
document.querySelectorAll('[data-action="ingest"]').forEach(btn => {
  btn.addEventListener('click', async () => {
    btn.textContent = 'Ingesting…';
    btn.disabled = true;
    const result = await api('/db/ingest', { method: 'POST' });
    btn.textContent = result?.status === 'ok'
      ? `✓ Done (${result.new_news} new articles, ${result.new_reddit} posts)`
      : '✗ Error';
    btn.disabled = false;
    // Reload forecast section
    sectionLoaded['forecast'] = false;
    if (currentSection() === 'forecast') loadForecast();
  });
});

// ── Section loader map ────────────────────────────────────────────────────────
const loaders = {
  dashboard:  loadDashboard,
  trends:     loadTrends,
  aesthetics: loadAesthetics,
  google:     loadGoogleTrends,
  colors:     loadColors,
  social:     loadSocial,
  news:       loadNews,
  brands:     loadBrands,
  calendar:   loadCalendar,
  forecast:   loadForecast,
  search:     loadSearch,
  ai:         loadAI,
};

// ── Bootstrap ────────────────────────────────────────────────────────────────
loadDashboard();
