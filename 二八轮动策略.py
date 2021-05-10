import numpy as np
import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import warnings
warnings.filterwarnings('ignore')

#设置参数
#计算N个交易日的涨跌幅
N = 20
#读取数据
data = pd.read_excel('指数行情序列.xlsx')
data = data.iloc[:-2,:]
#计算沪深300和中证500指数N个交易日的动量（momentum）
data["hs300_mom"]=data.沪深300.pct_change(periods = N)
data["zz500_mom"]=data.中证500.pct_change(periods = N)
#计算沪深300和中证500指数每天涨跌幅
data["hs300_dpct"] = data.沪深300/data.沪深300.shift(1) - 1
data["zz500_dpct"] = data.中证500/data.中证500.shift(1) - 1
#删除nan值
data.dropna(subset = ['hs300_mom'],inplace = True)

#根据策略设置调仓函数
def strategy(small, big):
    """调仓条件：满仓配置近20个交易日上涨较多的指数。若均下跌，则落袋为安。
      （此处先不考虑调仓时间的限制）
       small : 中证500指数
       big   : 沪深300指数 """

    if big < 0 and small < 0:
        return 'empty'
    if small > big:
        return 'zh500'
    if big > small:
        return 'hs300'
    else:
        return False

#为了减少调仓带来的手续费，限制两次调仓至少间隔十个交易日
#大小盘N日动量
big = data["hs300_mom"].values
small = data["zz500_mom"].values
#交易日（以index形式记录）
trade_day = data.index.values
#记录调仓的交易日（以index形式记录）
style_change_day = []
#记录每次调仓后的风格
style = []
for i in range(trade_day.shape[0]):
    #记录第一次"调仓"（申购）
    if i == 0:
        style.append(strategy(small[i],big[i]))
        style_change_day.append(trade_day[i])
    else:
        #在距上一次调仓日10个交易日以后才作判断
        if trade_day[i]-style_change_day[-1] >= 10:
            new_style = strategy(small[i],big[i])
            if new_style != style[-1]:
                style.append(new_style)
                style_change_day.append(trade_day[i])
#合并数据
style_pd = pd.DataFrame({'style':style},index =style_change_day)
df = data.join(style_pd,how = 'outer')
df['style'].fillna(method = 'ffill',inplace = True)
df['时间'] = pd.to_datetime(df['时间'],format='%Y-%m-%d')
#收盘才能确定style，持仓发生在style变动的后一天
df['pos']= df['style'].shift(1)
#调仓日期
df['relocate_time'] = df.loc[style_change_day,'时间']
#计算策略每日涨跌幅
df.loc[df['pos'] == 'zh500','strategy_dpct'] = df["zz500_dpct"]
df.loc[df['pos'] == 'hs300','strategy_dpct'] = df["hs300_dpct"]
df.loc[df['pos'] == 'empty','strategy_dpct'] = 0
#计算net(不考虑手续费情况下)
df['hs300_net'] = (df["沪深300"]/df["沪深300"].iloc[0])
df['zz500_net'] = (df["中证500"]/df["中证500"].iloc[0])
df['strategy_net'] = (1+df['strategy_dpct']).cumprod()
#对比策略，可视化结果（不考虑调仓费用）
sns.set(rc={'figure.figsize':(15, 5)})
sns.lineplot(x = pd.to_datetime(df['时间'].values), y = df['strategy_net'].values, label='strategy',color='#3c7f99')
sns.lineplot(x = pd.to_datetime(df['时间'].values), y = df['zz500_net'].values,label='zz500', color='#99533c')
sns.lineplot(x = pd.to_datetime(df['时间'].values), y = df['hs300_net'].values,label='hs300', color='#d39669')
plt.title('Strategy Results Without Transaction Fee',fontsize=20)
plt.show()

#计算net(考虑手续费情况下)
#调仓费率：申购费率0.12%，赎回费率0.375%（数据来源：支付宝「南方中证500ETF联接A」，赎回费率按持有7-180天的平均费率计算）
purchase_rate = 0.0012
sell_rate = 0.00375
#对策略产生的收益进行调整
df.loc[(df['relocate_time'].notnull())&(df['pos'] != 'empty')&
       (df['style'] == 'empty'),'strategy_dpct_adjust'] = (df['strategy_dpct'] + 1)*(1-sell_rate)-1
df.loc[(df['relocate_time'].notnull())&(df['pos'] == 'empty')&
       (df['style'] != 'empty'),'strategy_dpct_adjust'] = (df['strategy_dpct'] + 1)*(1-purchase_rate)-1
df.loc[(df['relocate_time'].notnull())&(df['pos'] != 'empty')&
       (df['style'] != 'empty'),'strategy_dpct_adjust'] = (df['strategy_dpct'] + 1)*(1-sell_rate)*(1-purchase_rate)-1
df.loc[df['relocate_time'].isnull(), 'strategy_dpct_adjust'] = df['strategy_dpct']
df['strategy_net_adjust'] = (1+df['strategy_dpct_adjust']).cumprod()

#对比策略，可视化结果(考虑调仓费用）
sns.set(rc={'figure.figsize':(15, 5)})
sns.lineplot(x = pd.to_datetime(df['时间'].values), y = df['strategy_net_adjust'].values, label='strategy',color='#3c7f99')
sns.lineplot(x = pd.to_datetime(df['时间'].values), y = df['zz500_net'].values,label='zz500', color='#99533c')
sns.lineplot(x = pd.to_datetime(df['时间'].values), y = df['hs300_net'].values,label='hs300', color='#d39669')
plt.title('Strategy Results Considering Transaction Fee',fontsize=20)
plt.show()


def evaluate_strategy(data, strategy, trade_time='2014-02-10 00:00:00'):
    """计算策略的年化收益率和最大回撤"""
    df = data.dropna(subset=['pos'])
    time = df[df.时间 >= trade_time].时间
    annual_return = (df[strategy].iloc[-1] ** (365 / (time.iloc[-1] - time.iloc[0]).days)) - 1
    # 计算当日之前的资金曲线的最高点
    df['max_values'] = df[strategy].expanding().max()
    # 计算与之前最高点的回撤
    df['retracement'] = df[strategy] / df['max_values'] - 1
    max_retrace = df.sort_values(by='retracement').iloc[0]['retracement']

    return annual_return, max_retrace

#评价策略效果
print('二八轮动策略（计算调仓费用）年化收益率为:',str(round(evaluate_strategy(df,'strategy_net_adjust')[0]*100,2)) + '%')
print('二八轮动策略（计算调仓费用）最大回撤为:',str(round(evaluate_strategy(df,'strategy_net_adjust')[1]*100,2)) + '%')
print('二八轮动策略（不计算调仓费用）年化收益率为:',str(round(evaluate_strategy(df,'strategy_net')[0]*100,2)) + '%')
print('二八轮动策略（不计算调仓费用）最大回撤为:',str(round(evaluate_strategy(df,'strategy_net')[1]*100,2)) + '%')
print('持有中证500年化收益率为:',str(round(evaluate_strategy(df,'zz500_net')[0]*100,2)) + '%')
print('持有中证500最大回撤为:',str(round(evaluate_strategy(df,'zz500_net')[1]*100,2)) + '%')
print('持有沪深300年化收益率为:',str(round(evaluate_strategy(df,'hs300_net')[0]*100,2)) + '%')
print('持有沪深300最大回撤为:',str(round(evaluate_strategy(df,'hs300_net')[1]*100,2)) + '%')

