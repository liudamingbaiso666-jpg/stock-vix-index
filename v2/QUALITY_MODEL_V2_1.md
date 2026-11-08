# V2.1 财务质量初筛（试验性）

运行入口：GitHub Actions → **V2 Financial Quality Screening** → Run workflow → main → mode=cases，batch=0。

## 改动
- 每个财务指标按**同一最近三个完整年度**对齐；缺失则 `unrated`，不再跳过缺失年度后拼接。
- 新增每股经营现金流三年正值检查、净利率检查、EPS可用时的经营现金流/每股收益比率观察。
- 毛利率为空时明确标记 `missing_fields`，**不以0代替，也不声称已经获取**。应在下一轮接入可靠备用财务来源。
- 资产负债率70%仅触发 `leverage_review`，不机械判定银行、公用事业或其他行业为差公司。
- 优先研究状态 `priority_review` 不代表质量认证，更不代表买入信号。
- 输出单独保存为 `v2/quality/YYYY-MM-DD/cases_quality_v2_1.json`，不会覆盖原始 `cases.json`。

## 分类
- `priority_review`: 最近三年ROE均不低于10%，盈利与经营现金流为正，未触发高负债复核。
- `ordinary_review`: 盈利与经营现金流为正，但ROE未达优先门槛。
- `leverage_review`: 资产负债率高于试验性70%门槛，需按行业复核。
- `risk_review`: 最近三年有非正盈利或经营现金流，须人工复核。
- `unrated`: 数据缺失或接口异常，不能作为负面结论。

## 注意
这不是800只股票的最终质量评价。尚未覆盖现金流量表总额、自由现金流、资本开支、资本回报、行业差异、财务重述、治理和商业模式；不适用于无时点数据校验的历史回测。优先先跑三家公司案例验证，再分批运行800只。
