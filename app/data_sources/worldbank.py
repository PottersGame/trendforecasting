"""World Bank Open Data API - completely free, no auth required."""

import requests
from typing import List, Dict, Any, Optional
from app.utils import cache


WB_API = 'https://api.worldbank.org/v2'

# Key economic indicators
INDICATORS = {
    'gdp_growth': 'NY.GDP.MKTP.KD.ZG',
    'inflation': 'FP.CPI.TOTL.ZG',
    'unemployment': 'SL.UEM.TOTL.ZS',
    'internet_users': 'IT.NET.USER.ZS',
    'mobile_subscriptions': 'IT.CEL.SETS.P2',
    'exports': 'NE.EXP.GNFS.ZS',
    'imports': 'NE.IMP.GNFS.ZS',
    'fdi': 'BX.KLT.DINV.WD.GD.ZS',
    'research_expenditure': 'GB.XPD.RSDV.GD.ZS',
    'renewable_energy': 'EG.FEC.RNEW.ZS',
    'co2_emissions': 'EN.ATM.CO2E.PC',
    'population': 'SP.POP.TOTL',
    'urban_population': 'SP.URB.TOTL.IN.ZS',
    'life_expectancy': 'SP.DYN.LE00.IN',
    'literacy_rate': 'SE.ADT.LITR.ZS',
}

TOP_ECONOMIES = ['US', 'CN', 'JP', 'DE', 'IN', 'GB', 'FR', 'BR', 'CA', 'KR']


def get_indicator_data(
    indicator: str,
    countries: Optional[List[str]] = None,
    start_year: int = 2010,
    end_year: int = 2023,
) -> List[Dict[str, Any]]:
    """Fetch indicator data from World Bank API."""
    if countries is None:
        countries = TOP_ECONOMIES

    indicator_code = INDICATORS.get(indicator, indicator)
    country_str = ';'.join(countries)

    cache_key = f'wb_{indicator}_{country_str}_{start_year}_{end_year}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f'{WB_API}/country/{country_str}/indicator/{indicator_code}'
    params = {
        'date': f'{start_year}:{end_year}',
        'format': 'json',
        'per_page': 500,
    }

    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code == 200:
            data = r.json()
            if len(data) >= 2:
                records = []
                for item in data[1] or []:
                    if item.get('value') is not None:
                        records.append({
                            'country': item.get('country', {}).get('value', ''),
                            'country_code': item.get('countryiso3code', ''),
                            'year': int(item.get('date', 0)),
                            'value': float(item.get('value', 0)),
                            'indicator': indicator,
                            'indicator_name': item.get('indicator', {}).get('value', ''),
                        })
                records.sort(key=lambda x: (x['country'], x['year']))
                cache.set(cache_key, records, ttl=3600)
                return records
    except Exception:
        pass

    return []


def get_global_trends_summary() -> Dict[str, Any]:
    """Get a summary of global economic trends."""
    cache_key = 'wb_global_summary'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    summary = {}

    key_indicators = ['gdp_growth', 'inflation', 'internet_users', 'renewable_energy', 'unemployment']
    for ind in key_indicators:
        data = get_indicator_data(ind, countries=['WLD', 'US', 'CN', 'IN'], start_year=2015, end_year=2022)
        if data:
            # Get latest world data
            world_data = [d for d in data if d['country_code'] in ['WLD', 'WLD']]
            if world_data:
                latest = sorted(world_data, key=lambda x: x['year'], reverse=True)
                summary[ind] = {
                    'latest_value': latest[0]['value'] if latest else None,
                    'latest_year': latest[0]['year'] if latest else None,
                    'trend': _calculate_trend([d['value'] for d in sorted(world_data, key=lambda x: x['year'])]),
                }

    cache.set(cache_key, summary, ttl=3600)
    return summary


def _calculate_trend(values: List[float]) -> str:
    """Calculate if a trend is increasing, decreasing, or stable."""
    if len(values) < 2:
        return 'stable'
    recent = values[-3:]
    if len(recent) < 2:
        return 'stable'
    change = (recent[-1] - recent[0]) / (abs(recent[0]) + 0.0001)
    if change > 0.05:
        return 'increasing'
    elif change < -0.05:
        return 'decreasing'
    return 'stable'


def get_country_comparison(indicator: str, year: int = 2021) -> List[Dict[str, Any]]:
    """Get country comparison for a specific indicator and year."""
    data = get_indicator_data(indicator, countries=TOP_ECONOMIES, start_year=year, end_year=year)
    return sorted(data, key=lambda x: x.get('value', 0), reverse=True)


def get_time_series(indicator: str, country: str = 'US') -> List[Dict[str, Any]]:
    """Get time series data for a specific indicator and country."""
    data = get_indicator_data(indicator, countries=[country], start_year=2000, end_year=2023)
    return sorted(data, key=lambda x: x['year'])
