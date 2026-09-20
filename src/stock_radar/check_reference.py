from datetime import date
from stock_radar.config import load_settings
import shioaji as sj

settings = load_settings(allow_production=True)
api = sj.Shioaji()
api.login(api_key=settings.api_key, secret_key=settings.secret_key)

symbols = ['2455', '3324', '3406', '3450', '4958']
print('=== 查詢個股今日參考價 (昨收價) 與今日收盤價 ===')

for s in symbols:
    contract = api.Contracts.Stocks[s]
    ref = getattr(contract, 'reference', None)
    limit_up = getattr(contract, 'limit_up', None)
    limit_down = getattr(contract, 'limit_down', None)
    print(f'{s} {contract.name}: 昨收參考價={ref} | 漲停價={limit_up} | 跌停價={limit_down}')

api.logout()