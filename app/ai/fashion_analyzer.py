"""
Fashion AI Analyst.

LLM priority chain (first available wins):
  1. Groq API  (llama3-8b-8192)      — set GROQ_API_KEY
  2. OpenAI    (gpt-3.5-turbo)       — set OPENAI_API_KEY
  3. Ollama    (local, any model)    — set OLLAMA_HOST / OLLAMA_MODEL (default llama3)
  4. Rule-based fallback             — always available, no keys needed

Every LLM call is augmented with RAG context fetched from the local SQLite
database before the prompt is sent, giving the model grounding in actual
news and Reddit data we have collected.
"""

from __future__ import annotations

import requests
from typing import List, Dict, Any, Tuple
from app.utils import cache

_SYSTEM = (
    'You are a senior fashion trend analyst and forecaster with deep expertise in '
    'global style movements, luxury fashion, streetwear, sustainability, and '
    'cultural aesthetics. You have access to real-time data from major fashion '
    'publications, Reddit communities, and search trends. '
    'Be concise, insightful, and editorial in tone.'
)


# ── LLM back-ends ─────────────────────────────────────────────────────────────

def _groq(prompt: str, api_key: str) -> str:
    r = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={'model': 'llama3-8b-8192',
              'messages': [{'role': 'system', 'content': _SYSTEM},
                           {'role': 'user', 'content': prompt}],
              'max_tokens': 450, 'temperature': 0.7},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content'].strip()


def _openai(prompt: str, api_key: str) -> str:
    r = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers={'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'},
        json={'model': 'gpt-3.5-turbo',
              'messages': [{'role': 'system', 'content': _SYSTEM},
                           {'role': 'user', 'content': prompt}],
              'max_tokens': 450, 'temperature': 0.7},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content'].strip()


def _ollama(prompt: str, host: str, model: str) -> str:
    """Call a locally-running Ollama instance."""
    r = requests.post(
        f'{host.rstrip("/")}/api/chat',
        json={'model': model,
              'messages': [{'role': 'system', 'content': _SYSTEM},
                           {'role': 'user', 'content': prompt}],
              'stream': False},
        timeout=120,
    )
    r.raise_for_status()
    return r.json()['message']['content'].strip()


def _llm(prompt: str) -> Tuple[str, str]:
    """Try Groq → OpenAI → Ollama in order. Returns (text, model_name)."""
    from flask import current_app
    groq_key     = current_app.config.get('GROQ_API_KEY', '')
    openai_key   = current_app.config.get('OPENAI_API_KEY', '')
    ollama_host  = current_app.config.get('OLLAMA_HOST', 'http://localhost:11434')
    ollama_model = current_app.config.get('OLLAMA_MODEL', 'llama3')

    if groq_key:
        try:
            return _groq(prompt, groq_key), 'groq/llama3-8b'
        except Exception:
            pass
    if openai_key:
        try:
            return _openai(prompt, openai_key), 'openai/gpt-3.5-turbo'
        except Exception:
            pass
    try:
        return _ollama(prompt, ollama_host, ollama_model), f'ollama/{ollama_model}'
    except Exception:
        pass
    return '', 'none'


# ── RAG context ────────────────────────────────────────────────────────────────

def _rag(subject: str) -> str:
    try:
        from app.database import get_context_for_ai
        ctx = get_context_for_ai(subject, max_items=8)
        return f'\n\n### Context from our fashion database:\n{ctx}\n' if ctx else ''
    except Exception:
        return ''


# ── Rule-based fallback ────────────────────────────────────────────────────────

_RULE: Dict[str, str] = {
    'Quiet Luxury': (
        'Quiet Luxury continues to dominate as consumers shift from logomania to '
        'understated craftsmanship in neutral palettes — ivory, camel, navy. '
        'Investment pieces from The Row, Loro Piana, and Brunello Cucinelli define '
        'the movement, whose near-term outlook remains strong as economic uncertainty '
        'drives demand for timeless, versatile wardrobes.'
    ),
    'Y2K Revival': (
        'The Y2K Revival is fuelled by Gen-Z nostalgia and relentless TikTok virality. '
        'Low-rise silhouettes, butterfly clips, sheer fabrics, and Juicy Couture '
        'tracksuits are key identifiers. Brands like Diesel, Miu Miu, and Versace '
        'are mining the early-2000s archive with strong commercial results.'
    ),
    'Mob Wife Aesthetic': (
        'Mob Wife erupted as a maximalist counter to Clean Girl minimalism, '
        'celebrating faux fur, animal print, bold gold jewellery, and dramatic '
        'silhouettes. Its TikTok virality signals strong short-term momentum, '
        'though saturation may accelerate its cultural decline.'
    ),
    'Balletcore': (
        'Balletcore translates the dance studio into daily dressing — wrap tops, '
        'satin flats, mesh layers, and pastel tones. High-fashion collaborations '
        'with Repetto and Miu Miu have pushed it into the mainstream with '
        'broad cross-demographic appeal.'
    ),
    'Sustainable Fashion': (
        'Sustainable Fashion has graduated from niche to necessity. Platforms '
        'like Depop, Vestiaire Collective, and ThredUp are accelerating, while '
        'EU legislation on extended producer responsibility is pushing brands '
        'toward greater transparency and circular design practices.'
    ),
    'Streetwear': (
        'Streetwear continues its luxury convergence — "luxe-casual" defines the '
        'moment. Limited drops, brand collabs, and sneaker culture drive intense '
        'engagement. Palace, Supreme, and Nike now compete with Dior and Louis '
        'Vuitton for the same cultural real-estate.'
    ),
    'Gorpcore': (
        'Gorpcore — outdoor technical wear as everyday fashion — is accelerating. '
        "Arc'teryx, Salomon, and Patagonia appear on runways and in editorial "
        'shoots, reflecting a fusion of function and style driven by urban '
        'consumers romanticising outdoor living.'
    ),
    'Dopamine Dressing': (
        'Dopamine Dressing channels joy through saturated colour — cobalt blues, '
        'cherry reds, electric yellows. It is a direct response to global '
        'uncertainty, treating clothing as a mood-regulation tool, and pairs '
        'naturally with maximalist styling movements.'
    ),
    'Athleisure': (
        'Athleisure remains a multi-billion-dollar category immune to cyclicality. '
        'Hybrid work has permanently cemented comfort-meets-style. Lululemon, '
        'Alo Yoga, and Vuori lead the premium segment; Nike and Adidas dominate '
        'the mass market with technically-enhanced lifestyle products.'
    ),
    'Clean Girl': (
        'Clean Girl prioritises effortless minimal beauty — slicked buns, dewy '
        'skin, gold jewellery, and neutral basics. It democratises luxury '
        'sensibility through social-media accessibility and underpins the most '
        'aspirational content on Instagram and TikTok.'
    ),
    'Coquette': (
        'Coquette distils hyper-femininity into bows, pink tones, and delicate '
        'accessories. Spawned from social-media subcultures, it celebrates '
        'romantic vulnerability and nostalgia for mid-century dressing through '
        'a thoroughly contemporary lens.'
    ),
    'Cottagecore': (
        'Cottagecore draws from rural romanticism with florals, prairie '
        'silhouettes, and artisanal detail. It resonates with younger consumers '
        'seeking an antidote to digital over-stimulation, sustaining steady '
        'search interest and community engagement.'
    ),
    'Dark Academia': (
        'Dark Academia merges intellectual aesthetics with gothic undertones — '
        'tweed blazers, turtlenecks, plaid, and rich earth tones. Its longevity '
        'is sustained by a literary and cinematic subculture that thrives on '
        'Tumblr, Pinterest, and niche Instagram communities.'
    ),
    'Coastal Grandmother': (
        'Coastal Grandmother evokes breezy, relaxed sophistication — linen '
        'trousers, oversized knitwear, espadrilles, and natural textures. '
        'The aesthetic has crossed age groups, appealing to anyone seeking '
        'polished, understated summer style without effort.'
    ),
    'Tomato Girl Summer': (
        'Tomato Girl Summer channels Mediterranean warmth through cherry-red '
        'palettes, sun-kissed skin, and Italian-coastal dressing. Its seasonal '
        'virality on TikTok makes it a strong summer driver for red-toned '
        'fashion and beauty purchases.'
    ),
    'Regencycore': (
        'Regencycore translates Bridgerton-era romanticism into modern dressing — '
        'empire waists, puff sleeves, pearl details, and pastel brocade. '
        'Its connection to ongoing streaming content gives it reliable '
        'cultural longevity beyond a single season.'
    ),
}

_GENERAL = (
    'The current fashion landscape is defined by a productive tension between '
    'maximalism and minimalism. Quiet Luxury and Clean Girl champion restraint '
    'while Mob Wife and Dopamine Dressing celebrate boldness. Social media '
    'compresses trend cycles dramatically, reducing seasonal relevance. '
    'Sustainability and the resale economy are reshaping ownership, with '
    'circular fashion growing fastest among under-35 demographics globally.'
)

_SEASONAL = {
    'Spring':  'Spring collections spotlight pastel palettes, floral prints, and lightweight layering. Transitional linen and organic cotton pieces dominate both runway and retail.',
    'Summer':  'Summer style leans into saturated brights, minimalist cuts, and resort-wear silhouettes. Beachwear and vacation dressing are elevated into genuine fashion categories.',
    'Fall':    'Fall runways foreground rich earthen tones, structured tailoring, and luxurious materials — leather, suede, and heavy-knit knitwear. Outerwear is the hero category.',
    'Winter':  'Winter fashion centres on statement outerwear, cosy textures, and a festive palette of deep burgundy, bottle green, and midnight navy with metallic accents.',
}


# ── Public API ─────────────────────────────────────────────────────────────────

def analyse_trend(trend_name: str) -> Tuple[str, str]:
    cache_key = f'ai_trend_{trend_name}'
    hit = cache.get(cache_key)
    if hit:
        return hit['text'], hit['model']

    context = _rag(trend_name)
    prompt = (
        f'{context}\n'
        f'Write a concise 3-sentence fashion trend analysis for "{trend_name}". '
        'Cover: what defines the look, who is driving it, and its near-term outlook. '
        'Ground your answer in the context data above where relevant.'
    )
    text, model = _llm(prompt)
    if not text:
        text, model = _RULE.get(trend_name, _GENERAL), 'rule-based'

    _persist('trend', trend_name, text, model)
    cache.set(cache_key, {'text': text, 'model': model}, ttl=1800)
    return text, model


def analyse_top_trends(trends: List[Dict[str, Any]]) -> Tuple[str, str]:
    top5 = [t['name'] for t in trends[:5]]
    cache_key = f'ai_overview_{"_".join(top5)}'
    hit = cache.get(cache_key)
    if hit:
        return hit['text'], hit['model']

    context = _rag(' '.join(top5))
    prompt = (
        f'{context}\n'
        f'The 5 most-discussed fashion trends right now are: {", ".join(top5)}. '
        'Write a 4-sentence editorial overview of what this says about the current '
        'cultural moment in fashion. Draw on the context data above.'
    )
    text, model = _llm(prompt)
    if not text:
        text = (f'Fashion today is led by {", ".join(top5[:3])} and '
                f'{", ".join(top5[3:])}. ' + _GENERAL)
        model = 'rule-based'

    _persist('overview', ','.join(top5), text, model)
    cache.set(cache_key, {'text': text, 'model': model}, ttl=1800)
    return text, model


def analyse_seasonal_outlook(season: str) -> Tuple[str, str]:
    cache_key = f'ai_season_{season}'
    hit = cache.get(cache_key)
    if hit:
        return hit['text'], hit['model']

    context = _rag(f'{season} fashion 2025')
    prompt = (
        f'{context}\n'
        f'Write a 3-sentence fashion forecast for {season} 2025. '
        'Cover key silhouettes, colours, and cultural influences. '
        'Use the context data above where relevant.'
    )
    text, model = _llm(prompt)
    if not text:
        text, model = _SEASONAL.get(season, _GENERAL), 'rule-based'

    _persist('season', season, text, model)
    cache.set(cache_key, {'text': text, 'model': model}, ttl=3600)
    return text, model


def generate_style_tip(trend_name: str) -> Tuple[str, str]:
    cache_key = f'ai_tip_{trend_name}'
    hit = cache.get(cache_key)
    if hit:
        return hit['text'], hit['model']

    prompt = (
        f'Give one practical "how to wear it" tip for the {trend_name} trend. '
        'Be specific about garments, colours, and occasion. Maximum 2 sentences.'
    )
    text, model = _llm(prompt)
    if not text:
        text = (f'To embody {trend_name}, focus on signature pieces that define '
                f'the look and pair them with classic staples for a balanced result.')
        model = 'rule-based'

    cache.set(cache_key, {'text': text, 'model': model}, ttl=3600)
    return text, model


def analyse_news_headlines(headlines: List[str]) -> Tuple[str, str]:
    if not headlines:
        return _GENERAL, 'rule-based'

    sample = headlines[:10]
    cache_key = f'ai_news_{"_".join(h[:15] for h in sample)}'
    hit = cache.get(cache_key)
    if hit:
        return hit['text'], hit['model']

    context = _rag('fashion industry trends news')
    hl_text = '\n'.join(f'- {h}' for h in sample)
    prompt = (
        f'{context}\n'
        f'Recent fashion headlines:\n{hl_text}\n\n'
        'Write a 3-sentence analysis of the key themes and what they signal '
        'about the direction of the fashion industry.'
    )
    text, model = _llm(prompt)
    if not text:
        text, model = _GENERAL, 'rule-based'

    _persist('news', 'latest_headlines', text, model)
    cache.set(cache_key, {'text': text, 'model': model}, ttl=1800)
    return text, model


def search_and_analyse(query: str) -> Tuple[str, str]:
    """
    Core RAG search: query our DB, inject results as context, ask the LLM
    to analyse and forecast what the data reveals about that fashion topic.
    """
    cache_key = f'ai_search_{query.lower()[:60]}'
    hit = cache.get(cache_key)
    if hit:
        return hit['text'], hit['model']

    try:
        from app.database import search_all
        results = search_all(query, limit=10)
    except Exception:
        results = {'news': [], 'reddit': []}

    news_lines   = [f"- [{a['source']}] {a['title']}" for a in results.get('news', [])]
    reddit_lines = [f"- [r/{p['subreddit']} ↑{p['score']}] {p['title']}"
                    for p in results.get('reddit', [])]

    ctx = ''
    if news_lines:
        ctx += 'News coverage:\n' + '\n'.join(news_lines[:6]) + '\n\n'
    if reddit_lines:
        ctx += 'Reddit discussion:\n' + '\n'.join(reddit_lines[:6])

    if not ctx:
        text  = (f'No data found in our database for "{query}" yet. '
                 'Ingest more data via /api/db/ingest to populate forecasts.')
        model = 'rule-based'
    else:
        prompt = (
            f'Based on the following data from our fashion database:\n\n{ctx}\n\n'
            f'Provide a 3-sentence trend analysis and short-term forecast for "{query}". '
            'Be specific about momentum, audience, and outlook.'
        )
        text, model = _llm(prompt)
        if not text:
            n_news   = len(results.get('news', []))
            n_reddit = len(results.get('reddit', []))
            text  = (f'Based on {n_news} news articles and {n_reddit} Reddit posts '
                     f'about "{query}", this topic is generating active discussion. ' + _GENERAL)
            model = 'rule-based'

    _persist('search', query, text, model)
    cache.set(cache_key, {'text': text, 'model': model}, ttl=900)
    return text, model


def get_ollama_models(host: str = 'http://localhost:11434') -> List[str]:
    """Return the list of locally available Ollama models."""
    try:
        r = requests.get(f'{host.rstrip("/")}/api/tags', timeout=5)
        if r.status_code == 200:
            return [m['name'] for m in r.json().get('models', [])]
    except Exception:
        pass
    return []


# ── Internal helper ────────────────────────────────────────────────────────────

def _persist(analysis_type: str, subject: str, content: str, model: str) -> None:
    try:
        from app.database import save_ai_analysis
        save_ai_analysis(analysis_type, subject, content, model)
    except Exception:
        pass
