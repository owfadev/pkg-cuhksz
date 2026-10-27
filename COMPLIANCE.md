# Compliance — why this package stays inside CUHK-SZ ITSO rules

> Reference basis for the package's behavioral boundaries. Full mapping page (with clause table): the OWFA instance doc `wiki/cuhksz/registry/itso.md`; primary sources: ITSO《香港中文大学（深圳）网络使用规定》(2024-05) and《IT资源管理规则》(2024-01) — [itso.cuhk.edu.cn](https://itso.cuhk.edu.cn/article/383).

ITSO publishes no clause named "crawler". Scraping behavior is covered by four existing provisions:

| ITSO risk surface | Clause | This package's actual behavior |
|---|---|---|
| Unauthorized access to IT facilities / credential theft | 《网络使用规定》第7条；《管理规则》第27条 | Own-credential, single-account, read-only pulls of pages the account is already entitled to see. No other-user credentials, no auth bypass, no endpoint probing |
| Port scanning / flooding / harming network operation (isolation clause) | 《管理规则》第31条 | On-demand, query-and-answer pulls only — no queues, no concurrency engine, no scheduled bulk jobs; one request stream at human pace |
| Mass download / redistribution of copyrighted works | 《网络使用规定》第4-5条；《管理规则》第26条 | Course files pulled on demand for the owner's study (the educational-use exception). Outputs relay in conversation or into the owner's private wiki — never republished, never exported to shared/public locations |
| Running unauthorized network services / proxies on campus network | 《网络使用规定》第6条；《管理规则》第30条 | Purely local CLI; no exposed service, no proxy, no external API |

Outer law layer: 《网络安全法》第27条 and《著作权法》— the campus clauses are their on-campus enforcement face.

## Usage rules (bind whoever operates this package)

1. Own credentials only — never operate with another person's account, and never act as a credential proxy for others
2. Human pace only — no bulk sweeps, no site-wide crawls, no concurrent request engines; if a fetch storm is foreseeable, split it across sessions
3. Personal study use for downloads — courseware and grades serve the owner's learning; do not bulk-reshare them (cloud drives, class-wide file dumps). Personal notes, the private wiki and in-conversation citation are fine
4. No external data services built on pulled data — do not turn fetched content into an API or proxy others consume
5. Relay, don't hoard personal data — sis fields stay in the identity page and conversation, per the sis-cli disclosure

Deliberately not provided: any write transaction (enroll/drop/swap, homework submission, announcements) — see the connector skills' scope sections.
