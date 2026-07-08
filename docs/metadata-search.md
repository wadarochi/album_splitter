# Metadata Search — Requirements & Implementation Status

## Search Requirements

cue-finder 的元数据搜索旨在为单文件整轨 CD 翻录（FLAC/WAV/APE）自动匹配专辑元数据，生成正确的 CUE sheet 并分轨。

### 核心要求

1. **精准匹配**：搜索到的专辑必须与音频文件的 track 边界对齐，时长匹配优先于文本匹配。
2. **中文标题**：对于华语专辑，优先返回中文曲目标题（繁体/简体均可），避免英文音译。
3. **多源交叉验证**：在多个元数据源之间交叉比选，通过打分仲裁而非简单取首个结果。
4. **Resilience**：当某源不可用、搜索无结果、或时长严重不匹配时，降级到其他源或本地备份。

### 匹配优先级

```
候选评分（P0） > 本地 CUE（P1） > 声纹仲裁（P4）
```

- `score_candidates()` 对每个候选计算 0–1 总分，融合：
  - 文本匹配等级（artist + title 与查询词的子集关系）— 权重 0.30
  - 时长对齐分数（DTW 匹配后置信度均值）— 权重 0.35
  - 曲目数差异 — 权重 0.15
  - 源可靠性权重 — 权重 0.10
  - AcoustID 指纹命中 — 权重 0.10
- 本地 CUE 自动发现优先级最高：若 `{input}.cue` 或 `{input}*.cue` 存在则直接解析。
- AcoustID 为可选增强：设置 `ACOUSTID_API_KEY` 后自动对音频指纹化，查询 AcoustID → 获取 MusicBrainz release MBID → 在评分中提升匹配到的 release。

---

## Implemented Sources

| Source | Status | Rate Limit | Notes |
|---|---|---|---|
| **MusicBrainz** | ✅ 正常 | 1 rps | 全球最大开放音乐数据库，中文支持有限，时长质量高 |
| **iTunes** | ✅ 正常 | 0.2s | 日韩华语覆盖好，中文标题常为日文汉字/拼音混合 |
| **NetEase 网易云** | ✅ 正常 | 0.2s | 华语最佳中文标题来源，通过 raw HTTP API（无 pyncm 依赖） |
| **Discogs** | ✅ 可选 | 1 rps | 需 `DISCOGS_TOKEN` 环境变量 |
| **Deezer** | ✅ 可选 | 0.2s | 无需认证 |
| **GnuDB** | ✅ 低权重 | 1 rps | 通过 MusicBrainz DiscID，时长质量差 |
| **AcoustID** | ✅ 可选 | 0.5s | 需 `ACOUSTID_API_KEY`，指纹→MB release 仲裁 |

### 已移除 / 不可用

| Source | Reason |
|---|---|
| **QQ Music** | `u.y.qq.com/cgi-bin/musicu.fcg` search 端点从当前测试环境返回 0 结果，疑似 IP/Cookie 限制；代码已移除 |

---

## 候选评分算法

实现位置：`cue_finder/core/rank.py`

```
total_score = 0.30 * text_score + 0.35 * duration_score + 0.15 * count_score
            + 0.10 * source_weight + 0.10 * fingerprint_score
```

- `text_score`：基于 artist + title token 与查询词的子集关系（0-4 级）
- `duration_score`：DTW 匹配后所有 track 置信度的均值
- `count_score`：1.0 − |detected_tracks − candidate_tracks| × 0.2
- `source_weight`：`{musicbrainz:1.0, netease:0.95, itunes:0.9, discogs:0.8, deezer:0.75, gnudb:0.6}`
- `fingerprint_score`：1.0 若候选 source_id ∈ AcoustID 返回的释放 MBID，否则 0.0

### TrackMatcher 改进

实现位置：`cue_finder/core/match.py`

1. **短片段合并**：检测到 < 15s 的短 segment 自动与相邻 segment 合并（通常是曲中静音假阳性）。
2. **相对时长 DTW**：cost 矩阵使用相对时长差 `|actual − expected| / max(expected, 1.0)`，使不同绝对长度但比例相似的曲目能正确对齐。
3. **跳过/共享**：DP 支持跳过告假的 detected segment（`skip_cost=0.5`）和共享 segment（`share_cost=0.05`），共享时按期望时长比例分割。
4. **移除 greedy fallback**：原逻辑在 DTW 置信度 < 0.5 时回退到贪婪匹配，该回退在新的相对时长 DTW 下反而产生更差结果，已移除。

---

## 本地 CUE 回退

实现位置：`cue_finder/core/cue.py::find_local_cue`

1. 检查 `{input_stem}.cue`（同目录、同文件名）
2. 若不存在，扫描同目录下 `{input_stem}*.cue`
3. 找到后直接解析 CUE（跳过搜索和评分）
4. 编码兼容：依次尝试 `utf-8-sig → utf-8 → gbk → big5 → latin1`
5. 通过 `--no-local-cue` 跳过本地 CUE，强制搜索

---

## S.H.E 批量评估结果

测试环境：Linux, `ACOUSTID_API_KEY` 未设, QQ Music/Kuwo 不可达。

| 专辑 | 匹配源 | 评分 | 状态 |
|---|---|---|---|
| ENCORE | NetEase | 0.69 | ✅ 中文标题 |
| 不想长大 | NetEase | 0.79 | ✅ 中文标题 |
| 美丽新世界 | NetEase | 0.58 | ✅ 中文标题 |
| 青春株式会社 | NetEase | 0.59 | ✅ 中文标题 |
| SHERO | NetEase | 0.73 | ✅ 中文标题 |
| 女生宿舍 | 本地 CUE | — | ✅ 本地 CUE 解析 |
| Super Star | NetEase | 0.44 | ✅ |
| 奇幻旅程 | NetEase | 0.52 | ✅ |
| Together | NetEase | 0.52 | ✅ |
| **Play** | iTunes | 0.42 | ⚠️ 英文标题（NetEase 无此专辑） |
| **我的电台** | NetEase | 0.38 | ⚠️ 分数偏低，时长差异大 |
| **Forever CD1** | MusicBrainz | 0.20 | ❌ 查询 `Forever CD1` 返回通用 CD1 |
| **Forever CD2** | iTunes 随机 | — | ❌ 查询失败 |

### 剩余问题

- **Play**：NetEase 搜索 `S.H.E Play` 返回无关结果（短英文专辑标题匹配差）。iTunes 有正确的 album 但标题为英文/拼音。需用 tracklist workflow 或手动创建中文 tracklist。
- **我的电台**：NetEase 返回 `我的电台 FM S.H.E`，但该版本时长与本地 FLAC 差异大，DJW 对齐后分割由分段比例插值，精度欠佳。
- **Forever CD1/CD2**：两个独立 FLAC 文件，文件名含 `CD1`/`CD2`，但搜索 `S.H.E Forever CD1` 在各源均无结果。需为每个 disc 单独准备 tracklist。

---

## 已知局限

- **华语短英文专辑标题**（如 `Play`、`Together`）在 NetEase/iTunes 搜索中易与无关专辑混淆。
- **跨源中文标题合并**：当 iTunes 有正确结构（时长、曲数）但英文标题，而 NetEase/MusicBrainz 有中文标题但结构不同时，无法自动取最优标题+结构组合。
- **AcoustID 未实际验证**：代码已实现，但因无 API key 未经线上测试。
- **Chromaprint 后端依赖**：`acoustid.fingerprint_file()` 需要 `fpcalc` 或 `chromaprint` + `audioread`，非 pip 安装。
- **声纹仲裁粒度**：当前仅按 release MBID 提升已有候选的分数，不主动从 AcoustID 录音 ID 构造新候选。

---

## 下一步

1. 为 Play / 我的电台 / Forever CD1&2 创建 tracklist YAML。
2. 获取 `ACOUSTID_API_KEY` 并验证声纹仲裁流程。
3. 研究跨源中文标题丰富化（iTunes 结构 + NetEase/MusicBrainz 中文标题）。
