"""
Fashion AI Analyst.

Priority chain:
  1. Groq API (llama3-8b-8192)  — free, fast, set GROQ_API_KEY
  2. OpenAI (gpt-3.5-turbo)     — set OPENAI_API_KEY
  3. Rule-based fallback         — always available, no keys needed

All LLM calls are cached for 30 minutes to conserve quota.
"""

from __future__ import annotations

import re
import json
import requests
from typing import List, Dict, Any
from app.utils import cache

# ── LLM helpers ───────────────────────────────────────────────────────────────

def _groq_complete(prompt: str, api_key: str) -> str:
    """Call Groq Chat Completions endpoint."""
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': 'llama3-8b-8192',
        'messages': [
            {'role': 'system', 'content': (
                'You are a senior fashion trend analyst with expertise in style forecasting, '
                'cultural movements, and the global fashion industry. '
                'Provide concise, insightful analysis in a professional yet engaging tone.'
            )},
            {'role': 'user', 'content': prompt},
        ],
        'max_tokens': 400,
        'temperature': 0.7,
    }
    r = requests.post(
        'https://api.groq.com/openai/v1/chat/completions',
        headers=headers, json=payload, timeout=20,
    )
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content'].strip()


def _openai_complete(prompt: str, api_key: str) -> str:
    """Call OpenAI Chat Completions endpoint."""
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': 'gpt-3.5-turbo',
        'messages': [
            {'role': 'system', 'content': (
                'You are a senior fashion trend analyst. '
                'Provide concise, insightful analysis in a professional tone.'
            )},
            {'role': 'user', 'content': prompt},
        ],
        'max_tokens': 400,
        'temperature': 0.7,
    }
    r = requests.post(
        'https://api.openai.com/v1/chat/completions',
        headers=headers, json=payload, timeout=20,
    )
    r.raise_for_status()
    return r.json()['choices'][0]['message']['content'].strip()


def _llm_complete(prompt: str) -> str | None:
    """Try Groq → OpenAI in order; return None if both unavailable."""
    from flask import current_app
    groq_key   = current_app.config.get('GROQ_API_KEY', '')
    openai_key = current_app.config.get('OPENAI_API_KEY', '')
    if groq_key:
        try:
            return _groq_complete(prompt, groq_key)
        except Exception:
            pass
    if openai_key:
        try:
            return _openai_complete(prompt, openai_key)
        except Exception:
            pass
    return None


# ── Rule-based fallback insights ──────────────────────────────────────────────

_RULE_INSIGHTS: Dict[str, str] = {
    'Quiet Luxury': (
        'Quiet Luxury continues its dominance as consumers gravitate toward '
        'understated elegance and quality over logomania. Investment pieces in '
        'neutral palettes — ivory, camel, navy — are at the core of this movement, '
        'driven by a post-pandemic desire for timeless, long-lasting wardrobes.'
    ),
    'Y2K Revival': (
        'The Y2K Revival shows no signs of slowing, fuelled by Gen-Z nostalgia and '
        'social-media virality on TikTok and Instagram. Low-rise silhouettes, '
        'butterfly clips, bedazzled accessories, and sheer fabrics are key markers. '
        'Brands from Diesel to Juicy Couture are capitalising on the reboot.'
    ),
    'Mob Wife Aesthetic': (
        'The Mob Wife Aesthetic erupted as a counter-movement to Clean Girl minimalism '
        'embracing maximalism: faux fur, leopard print, gold jewellery, and '
        'dramatic silhouettes. It taps into a cultural appetite for unapologetic '
        'glamour and bold self-expression.'
    ),
    'Balletcore': (
        'Balletcore translates ballet-studio staples into everyday dressing — '
        'wrap tops, satin ballet flats, mesh fabrics, and pastel tones. '
        'Collaboration between dancewear brands and high-fashion houses has '
        'accelerated mainstream adoption.'
    ),
    'Sustainable Fashion': (
        'Sustainable Fashion has evolved from niche to necessity. Secondhand platforms '
        'like Depop and Vestiaire Collective are growing rapidly, while luxury brands '
        'roll out repair services and recycled materials programmes. Regulation in the '
        'EU is also pushing brands toward greater transparency.'
    ),
    'Streetwear': (
        'Streetwear continues to merge with luxury — "luxe-casual" defines the moment. '
        'Limited-edition drops, brand collaborations, and sneaker culture drive '
        'engagement. Key players: Nike, Adidas, New Balance, Palace, and Supreme '
        'alongside luxury houses adopting drop models.'
    ),
    'Gorpcore': (
        'Gorpcore — outdoor technical wear worn as everyday fashion — is expanding '
        'beyond its niche origins. Arc\'teryx, Salomon, and Patagonia are appearing '
        'on runways and editorial shoots, reflecting a fusion of function and style.'
    ),
    'Dopamine Dressing': (
        'Dopamine Dressing channels joy through bold, saturated colour. '
        'Cobalt blues, electric yellows, and cherry reds dominate. '
        'The trend is a direct response to global uncertainty, '
        'with consumers using clothing as a mood-lifting tool.'
    ),
    'Athleisure': (
        'Athleisure remains a multi-billion-dollar category that defies cyclicality. '
        'The hybrid work model has cemented comfort-meets-style as a lasting wardrobe '
        'philosophy. Lululemon, Alo Yoga, and Vuori lead the premium segment.'
    ),
    'Cottagecore': (
        'Cottagecore draws from rural romanticism with floral prints, prairie silhouettes '
        'and artisanal details. It aligns with a broader desire for slower living and '
        'connection to nature, resonating especially with younger audiences online.'
    ),
    'Clean Girl': (
        'The Clean Girl aesthetic prioritises effortless, minimal beauty and style: '
        'slicked-back buns, dewy skin, neutral basics, gold jewellery. '
        'It democratises luxury sensibility and has become a cornerstone of '
        'aspirational social-media content.'
    ),
    'Coastal Grandmother': (
        'Coastal Grandmother evokes breezy, relaxed sophistication — linen trousers, '
        'oversized knitwear, espadrilles, and natural textures. The aesthetic has been '
        'embraced across age groups seeking polished yet understated summer style.'
    ),
    'Dark Academia': (
        'Dark Academia merges intellectual aesthetics with gothic undertones — '
        'tweed blazers, turtlenecks, plaid, and rich earth tones. Its popularity '
        'is sustained by a literary and cinematic cultural subculture that thrives '
        'on social media platforms.'
    ),
}

_GENERAL_INSIGHT = (
    'The current fashion landscape is characterised by a tension between maximalism '
    'and minimalism. While Quiet Luxury and Clean Girl aesthetics champion restraint, '
    'Mob Wife and Dopamine Dressing celebrate boldness. Social media continues to '
    'accelerate trend cycles, compressing seasonal timelines. Sustainability and '
    'resale culture are reshaping how consumers relate to clothing ownership.'
)

_SEASONAL_INSIGHTS = {
    'Spring':  'Spring collections spotlight pastel palettes, floral prints, and '
               'lightweight layering. Transitional pieces in linen and cotton dominate.',
    'Summer':  'Summer style leans into saturated brights, minimalist cuts, and '
               'resort-wear silhouettes. Beachwear and vacation dressing are elevated.',
    'Fall':    'Fall runways foreground rich earthen tones, structured tailoring, '
               'and luxurious fabrics — leather, suede, and heavy-knit knitwear.',
    'Winter':  'Winter fashion is defined by statement outerwear, cosy textures, '
               'and a festive palette of deep burgundy, bottle green, and midnight navy.',
}


# ── Public API ─────────────────────────────────────────────────────────────────

def analyse_trend(trend_name: str) -> str:
    """Return a 2–4 sentence analysis of a specific fashion trend."""
    cache_key = f'ai_trend_{trend_name}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    prompt = (
        f'Write a concise 3-sentence fashion trend analysis for "{trend_name}". '
        'Include: what defines the look, who is driving it, and its near-term outlook. '
        'Keep the tone professional and editorial.'
    )
    text = _llm_complete(prompt)
    if not text:
        text = _RULE_INSIGHTS.get(trend_name, _GENERAL_INSIGHT)

    cache.set(cache_key, text, ttl=1800)
    return text


def analyse_top_trends(trends: List[Dict[str, Any]]) -> str:
    """Summarise the top 5 trends currently dominating fashion."""
    top5 = [t['name'] for t in trends[:5]]
    cache_key = f'ai_top_trends_{"_".join(top5)}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    prompt = (
        f'The 5 most-discussed fashion trends right now are: {", ".join(top5)}. '
        'Write a 4-sentence editorial overview explaining what this says about '
        'the current cultural moment in fashion. Be insightful and specific.'
    )
    text = _llm_complete(prompt)
    if not text:
        text = (
            f'The current fashion conversation is dominated by {", ".join(top5[:3])} '
            f'and {", ".join(top5[3:])}. '
            + _GENERAL_INSIGHT
        )

    cache.set(cache_key, text, ttl=1800)
    return text


def analyse_seasonal_outlook(season: str) -> str:
    """AI outlook for the current or specified season."""
    cache_key = f'ai_season_{season}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    prompt = (
        f'Write a 3-sentence fashion forecast for {season} 2025. '
        'Cover key silhouettes, colours, and cultural influences shaping the season. '
        'Keep it concise and editorial in tone.'
    )
    text = _llm_complete(prompt)
    if not text:
        text = _SEASONAL_INSIGHTS.get(season, _GENERAL_INSIGHT)

    cache.set(cache_key, text, ttl=3600)
    return text


def generate_style_tip(trend_name: str) -> str:
    """Generate a practical 'how to wear it' style tip for a trend."""
    cache_key = f'ai_tip_{trend_name}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    prompt = (
        f'Give one practical "how to wear it" style tip for the {trend_name} trend. '
        'Be specific about garments, colours, and occasion. Maximum 2 sentences.'
    )
    text = _llm_complete(prompt)
    if not text:
        # Generic tip based on trend name
        text = (
            f'To embody {trend_name}, focus on key signature pieces that define the look '
            f'and pair them with classic wardrobe staples for a balanced, wearable result.'
        )

    cache.set(cache_key, text, ttl=3600)
    return text


def analyse_news_headlines(headlines: List[str]) -> str:
    """Summarise what fashion news headlines reveal about industry direction."""
    if not headlines:
        return _GENERAL_INSIGHT

    sample = headlines[:10]
    cache_key = f'ai_news_{"_".join(h[:20] for h in sample)}'
    hit = cache.get(cache_key)
    if hit is not None:
        return hit

    headlines_text = '\n'.join(f'- {h}' for h in sample)
    prompt = (
        f'Based on these recent fashion headlines:\n{headlines_text}\n\n'
        'Write a 3-sentence analysis of the key themes and what they signal '
        'about the direction of the fashion industry right now.'
    )
    text = _llm_complete(prompt)
    if not text:
        text = _GENERAL_INSIGHT

    cache.set(cache_key, text, ttl=1800)
    return text
