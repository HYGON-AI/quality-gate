# Repository profiles

Each caller is explicitly registered by one YAML file named
`OWNER_REPOSITORY.yaml`.

每个接入仓库都必须显式登记，文件名为 `OWNER_REPOSITORY.yaml`，至少确认：

- repository：必须与 GitHub `owner/repository` 完全一致；
- repository_mode：必须是 `original`、`fork`、`submodule-patch` 或 `overlay`；
- policy：当前发布的 PR 门禁规则 ID；
- license：仓库适用的 SPDX License ID；
- legal_files：不得被 PR 删除或重写的法律文件；
- third_party_registries：第三方来源登记文件；
- third_party_paths：第三方源码目录；
- generated_paths：只提示、不机械要求源码头的生成文件；
- hygon_owned_paths：明确属于 HYGON 原创、必须使用仓库文件头的路径；
- upstream_paths：继承的上游源码路径，不机械添加 HYGON 原创文件头；
- patch_paths：外部补丁路径，不机械添加 HYGON 原创文件头。

## Repository modes / 仓库模式

| Mode / 模式 | 新增但未归类源码的默认处理 |
| --- | --- |
| `original` | 按 HYGON 原创处理，缺少 HYGON Copyright 或仓库 SPDX 时阻断 |
| `fork` | 报告来源待确认，不机械添加 HYGON 文件头，不阻断 |
| `submodule-patch` | 已登记的上游和补丁路径跳过原创头；其他新增源码按 HYGON 原创处理 |
| `overlay` | 已登记的上游和补丁路径跳过原创头；其他新增源码按 HYGON 原创处理 |

路径分类优先于模式默认值。新增第三方代码仍应登记
`third_party_paths` 和 `third_party_registries`；生成文件应登记
`generated_paths`。

Profiles are reviewed policy, not caller-controlled inputs. Do not allow a pull
request from the target repository to replace its central profile at runtime.
