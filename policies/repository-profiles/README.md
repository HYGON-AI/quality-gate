# Repository profiles

Each caller is explicitly registered by one YAML file named
`OWNER_REPOSITORY.yaml`.

每个接入仓库都必须显式登记，文件名为 `OWNER_REPOSITORY.yaml`，至少确认：

- repository：必须与 GitHub `owner/repository` 完全一致；
- policy：当前发布的 PR 门禁规则 ID；
- license：仓库适用的 SPDX License ID；
- legal_files：不得被 PR 删除或重写的法律文件；
- third_party_registries：第三方来源登记文件；
- third_party_paths：第三方源码目录；
- generated_paths：只提示、不机械要求源码头的生成文件。

Profiles are reviewed policy, not caller-controlled inputs. Do not allow a pull
request from the target repository to replace its central profile at runtime.
