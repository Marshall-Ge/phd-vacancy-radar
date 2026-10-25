# PhD Vacancy Radar

博士项目 + funding / PI 雷达。核心逻辑来自你给的 Excel：

> 带薪博士项目的前提是「导师已经有 funding」。所以除了刷招聘网站，还要**反着找**：先盯 ERC / DFG / NWO 等新获 funding 的项目和 PI，再去 PI 的团队主页找项目。

- **有新项目** → 立即发邮件（项目 / funding 分开算分，达到阈值才打扰你）；
- **每 5 天** → 发一次汇总（即使没有新增也发，证明监控还活着）；
- 支持 **1–2 个收件邮箱**；
- 5 天汇总可带 **CSV / HTML 附件**（完整清单，CSV 可直接用 Excel 打开）；
- 跑在 GitHub Actions 云端，不依赖你的电脑和本地网络。

![5 天汇总邮件示例](docs/digest_preview.png)

---

## 一、它监控什么

### 自动监控（默认开启）

| 源 | 地区 | 抓什么 | 方式 |
| --- | --- | --- | --- |
| **jobs.ac.uk** | 英国 | PhD / doctoral / studentship 项目 | 搜索页 HTML |
| **AcademicTransfer** | 荷兰 | 带薪博士项目（含薪资、截止日期） | sitemap + 详情页 JSON-LD |
| **University of Copenhagen** | 丹麦 | PhD / doctoral 项目 | 招聘页 HTML |
| **GEPRIS (DFG)** | 德国 | 当前在研项目、PI、机构、项目类型 | 前端检索接口 |
| **NWO** | 荷兰 | 已获 funding 的项目、PI、机构、funding 计划 | 官方 NWOpen API |
| **UKRI GtR** | 英国 | 已获 funding 的项目、机构、funding 方 | 官方 API |

### 手动入口（邮件底部常驻）

EURAXESS、FindAPhD、Academic Positions、LinkedIn Jobs、ERC 项目库、DFF、Research Portal Denmark、各大学招聘页。

> 这些站点要么有 Cloudflare / 登录 / 地区限制，要么没有稳定 API；强行抓取容易失效。工具会把它们作为「手动检索入口」放在每封邮件底部，并把自动源的失败情况写进状态表。

### 打分逻辑

你的画像写在 [config.toml](config.toml)：

- **主题**：信息系统、数字化转型、数据驱动决策、商业分析、管理与组织、技术采纳、数字创新、平台等；
- **方法**：定量、因果推断、计量、统计、实验、实证、机器学习等；
- **国家加分**：NL / DK +3，DE +2，UK / SE / BE 等 +1；
- **资金信号**：出现 salary / funded / employment contract 等 +1.5，自费/学费风险 -6；
- **标题硬门槛**：项目标题必须命中目标主题，否则直接丢弃（避免「生物/物理/工程项目正文里出现 management」被误收）。

项目 ≥ **5.0**、funding ≥ **8.0** 时，立即发邮件；其余进 5 天汇总。

首次运行只建立基线（并把当前项目/funding 记入 state），不会把历史积压一次性当「新项目」轰炸你；从第二次运行开始才按上面的阈值即时提醒。

---

## 二、邮件长什么样

**立即告警**（有新项目 / 新 funding 时）：

```
主题：[PhD Radar] 发现 2 个新项目/funding（项目 1 / funding 1）

- [7.5] PhD Position in Digital Transformation ...
  TU Delft · NL · 截止 2026-11-18
  薪资/经费：€3,204–4,051
  匹配：主题：digital transformation、business analytics
  链接：...
```

**5 天汇总**：本期所有首次发现的项目 + funding / PI + 手动入口 + 监控源状态。前 8 条用详细卡片，其余用紧凑清单（每类最多 150 条），已即时提醒过的也会保留在汇总里，尽量不漏。

附件（默认 CSV，可改 `html` / `both`）：

- `phd-radar-YYYY-MM-DD.csv`：完整字段（类型、分数、标题、机构、国家、PI、截止、薪资、主题、方法、链接、摘要），UTF-8 BOM，Excel 直接打开不乱码；
- `phd-radar-YYYY-MM-DD.html`：完整清单表格，链接可点击。

funding 项目会附：

- PI 姓名、机构、项目类型、起止年份；
- 详情页链接；
- 一键 Google `"PI 姓名" PhD position`，方便去团队主页找项目。

---

## 三、部署（10 分钟）

1. 新建 GitHub 仓库（建议 **Public**，Actions 分钟数免费），把本项目上传；
2. **Settings → Actions → General**：允许 Actions，Workflow permissions 选 **Read and write**；
3. **Settings → Secrets and variables → Actions → Secrets** 添加：
   - `MAIL_TO`：1–2 个邮箱，逗号分隔，例如 `a@163.com,b@qq.com`
   - `MAIL_USERNAME`：发件邮箱（163 / QQ 均可）
   - `MAIL_PASSWORD`：邮箱的 SMTP 授权码
4. 跑一次 **Actions → Run workflow → test-email**，确认收信；
5. 再跑一次 **check**，会收到「监控已启动」+ 当前基线。

之后每小时自动检查；有新项目立即发信，每 5 天汇总。

> 163 授权码：设置 → POP3/SMTP/IMAP → 开启 SMTP → 获取授权码。
> QQ 授权码：设置 → 账号与安全 → 开启 POP3/SMTP → 短信验证 → 16 位授权码。
> 想换 QQ：`config.toml` 里 `smtp_host = "smtp.qq.com"`。

---

## 四、暂停 / 恢复 / 重置状态

不用改代码，直接在 **Actions → Run workflow** 里选模式：

| 模式 | 作用 |
| --- | --- |
| `stop` | 软暂停：之后每小时仍会启动 workflow，但**不抓取、不发信**，直接跳过 |
| `resume` | 恢复监控 |
| `reset` | 清空 `state.json`（已见项目/funding、告警记录、计时），下一次 `check` 重新建立基线并发送「监控已启动」 |

说明：

- `stop` 只是软暂停，Actions 仍会每小时跑一次（每次几秒）；想彻底停止运行和计费，去 **Actions 页面右上角 ⋯ → Disable workflow**。
- `reset` 不会删除代码和 `config.toml`，只重置状态；重置后不会把存量当新项目轰炸，因为下一次运行会重新走「首次基线」。
- 暂停期间手动跑 `digest` 也会被跳过；要先 `resume`。
- 这些操作都会修改并提交 `state.json`，所以 Workflow permissions 必须是 **Read and write**。

本地等价命令：

```bash
python -m phd_radar stop
python -m phd_radar resume
python -m phd_radar reset
```

---

## 五、配置

| 配置 | 默认 | 说明 |
| --- | --- | --- |
| `monitor.alert_score` | 5.0 | 新项目立即告警阈值 |
| `monitor.award_alert_score` | 8.0 | 新 funding 立即告警阈值 |
| `monitor.digest_every_days` | 5 | 汇总间隔 |
| `monitor.digest_max_items` | 150 | 汇总每类最多列多少条（尽量全） |
| `monitor.digest_detail_items` | 8 | 其中前几条用详细卡片 |
| `monitor.digest_attachment` | csv | 汇总附件：csv / html / both / none |
| `monitor.digest_hour` | 9 | 汇总在本地时间几点后发 |
| `profile.topics` | 见文件 | 主题词；改这里就能换方向 |
| `profile.country_bonus` | NL/DK 3… | 国家偏好 |
| `source.enabled` | true | 关掉某个源 |

想加大学招聘页：复制 `uni_page` 那段，填 `url`、`institution`、`country`、`href_contains` 即可。

---

## 六、本地运行

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
MAIL_PROVIDER=none python -m phd_radar check --dry-run   # 只抓取、打印，不发信
python -m unittest discover -s tests -v
```

---

## 七、已知限制

- **EURAXESS / FindAPhD / Academic Positions / LinkedIn** 有 Cloudflare、登录或地区限制，未做自动抓取；邮件底部保留入口。
- **GEPRIS** 用的是网页前端检索接口，不是正式公开 API；已限速并只取在研项目，如遇改版需调整。
- **AcademicTransfer** 只抓最新 + 商科相关 slug 的项目（每次约 20 个详情页），不是全量。
- **项目** 以「带薪雇员 PhD」为主；英国 studentship 会标注 funding 情况，但学费/生活费是否覆盖需点开原页面确认。
- 所有判断都是关键词 + 规则，**不替代人工阅读**；邮件里的「匹配」只是筛选线索。
- 云端 IP 仍可能被个别站点临时封禁；连续失败会在状态表里标红。

---

## 八、数据来源

- 招聘：jobs.ac.uk、AcademicTransfer、University of Copenhagen
- funding：DFG GEPRIS、NWO NWOpen API、UKRI Gateway to Research
- 手动：EURAXESS、FindAPhD、Academic Positions、LinkedIn、ERC、DFF、Research Portal Denmark

*非官方工具；请遵守各网站的使用条款。*
