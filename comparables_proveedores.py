"""Candidatos FMP/Finnhub opcionales; nunca certifican comparabilidad ni ratios."""
import os
import re
import requests


def yahoo_symbol(value):
    """Conservar sufijos Yahoo conocidos; no adivinar bolsa para símbolos ajenos."""
    value = str(value or '').strip().upper()
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.\-]{0,24}', value):
        return None
    if re.fullmatch(r'[A-Z]+\.[AB]', value):
        return value.replace('.', '-')
    if '.' in value and value.rsplit('.', 1)[1] not in {
        'KS', 'KQ', 'TW', 'TWO', 'T', 'L', 'DE', 'PA', 'AS', 'MC', 'MI',
        'SW', 'HK', 'TO', 'V', 'AX', 'NS', 'BO', 'SI', 'ST', 'HE', 'CO', 'OL',
    }:
        return None
    return value


def provider_candidates(ticker, *, get=None, env=None):
    """Máximo dos peticiones de 12 s. Caché 72 h si el dashboard la configura.

    Las claves no se incluyen en la caché, mensajes de error ni evidencias.
    Un fallo de autenticación/cobertura no impide usar Yahoo.
    """
    env = os.environ if env is None else env
    get = requests.get if get is None else get
    candidates, errors = {}, []
    sources = [
        ('FMP', env.get('FMP_API_KEY'),
         'https://financialmodelingprep.com/stable/stock-peers',
         {'symbol': ticker}, 'apikey'),
        ('Finnhub', env.get('FINNHUB_API_KEY'),
         'https://finnhub.io/api/v1/stock/peers',
         {'symbol': ticker, 'grouping': 'subIndustry'}, 'token'),
    ]
    for name, key, url, params, auth in sources:
        if not key:
            continue
        try:
            def fetch():
                response = get(url, params={**params, auth: key}, timeout=12)
                if response.status_code != 200:
                    raise ValueError('HTTP ' + str(response.status_code))
                data = response.json()
                if not isinstance(data, list):
                    raise ValueError('Respuesta no válida o acceso no incluido')
                return data
            path = env.get('VALUACION_SOURCE_CACHE')
            if path:
                from seguimiento_store import Store, TTL
                data = Store(path).cached('peer-discovery:v1:' + name + ':' + ticker,
                    fetch, TTL['peers'], env.get('VALUACION_SOURCE_FORCE') == '1')
            else:
                data = fetch()
            for item in data[:40]:
                raw = item.get('symbol') if isinstance(item, dict) else item
                symbol = yahoo_symbol(raw)
                if symbol and symbol != ticker.upper():
                    candidates.setdefault(symbol, {'Ticker': symbol,
                        'Origen candidatos': 'Peers ' + name,
                        'Prioridad origen': -3, 'Capitalización de screener': None})
            if not data:
                errors.append(name + ': sin cobertura para este símbolo')
        except Exception as exc:
            # requests puede incluir una URL con la clave en str(exc).
            detail = str(exc) if isinstance(exc, ValueError) and str(exc).startswith('HTTP ') else type(exc).__name__
            errors.append(name + ': ' + detail + '; continúa Yahoo')
    return candidates, errors
