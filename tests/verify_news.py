import sys
import types

sys.modules['requests'] = types.SimpleNamespace(get=lambda *args, **kwargs: types.SimpleNamespace(json=lambda: {'status': 'ok', 'articles': [{'title': 'Demo title', 'source': {'name': 'Demo Source'}}]}))
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda *args, **kwargs: None)

import news

print(news.parse_date_input('16-july-2026'))
print(news.get_news_for_request('tell me current news about m.s dhoni').splitlines()[0])
print(news.get_news_for_request('main news for 16 july 2026').splitlines()[0])
