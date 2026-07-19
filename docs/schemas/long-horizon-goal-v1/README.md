# ArchCritic 长程 Goal v1 数据模板

本目录定义基准样本、知识卡、公共建筑案例和来源授权的机器可读字段。它们不包含任何真实教师分、学生身份或人工标注答案。

## 严格数据分层

```text
benchmark-v3/
├── model-inputs/          # 评图进程唯一可读，只含匿名图纸和任务书
├── run-results/           # 评图进程写入，正式运行后冻结
├── public-manifests/      # 不含答案的样本、模型和版本清单
├── private-answers/       # 裁判进程专用，评图进程不可读
└── evaluation-results/    # 分数冻结后由独立裁判进程生成
```

正式最终测试必须使用两个独立命令：

1. `blind-run`：只读 `model-inputs`，生成并冻结评图结果。
2. `blind-judge`：在评图结果冻结后，再读 `private-answers` 做统计和语义裁判。

不得让同一评图进程同时拥有模型输入与最终测试答案路径。

## 分档口径

- 低分档：教师分低于 75。
- 中档：教师分为 75—89.99。
- 高分档：教师分为 90 及以上。

该口径只在私有答案侧使用，不得写入模型输入、图纸文件名、项目名或任务书摘要。

## 模板对应关系

- `benchmark-model-input.schema.json`：被测 Agent 可读的匿名输入。
- `benchmark-private-answer.schema.json`：只由冻结后裁判流程读取的私有答案。
- `source-record.schema.json`：书籍、规范、项目页和媒体文件的来源与授权。
- `knowledge-card.schema.json`：三个层级的可追溯教学知识卡。
- `knowledge-question.schema.json`：三层固定问答、依据定位和禁止编造检查。
- `public-building-case.schema.json`：公共建筑案例和深度分析字段。

字段未填写、来源未审核或授权不明的内容，可以保存为草稿，但不得计入 Goal 验收数量。
