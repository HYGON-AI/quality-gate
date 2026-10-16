# Gitlink 和 SPDX 表达式增量检查修复

## 范围与策略边界

修复父仓库增量门禁读取 Git 子模块指针时错误报告对象缺失，以及将 SPDX
表达式变更统称为 Copyright 删除的问题。不修改已有 GitHub 接入方式，不发布
新版本、不移动 stable 标签，也不增加默认许可证准入范围。

Git 差异范围通过 raw diff 保留旧/新 mode 和对象 ID。mode 160000 的目标是
Gitlink，在父仓库记录路径和旧/新 Commit，不读取为文件、不自动下载子模块。
报告明确披露子模块内部源码未扫描。新增/重命名路径的字段检查仍执行；
Gitlink 转普通文件时继续扫描内容，不按 third-party 目录名豁免。

SPDX 使用有长度、token 数与嵌套深度上限的表达式解析器，区分 AND、OR、WITH
和括号。解析成功仅代表语法可识别，不代表许可证或组合已获准入审批。
单独的 MIT、BSD-3-Clause、Apache-2.0 维持现状；复合表达式默认仍阻断待审核。

集中策略新增 `license_admission.approved_expressions`，默认空列表。只有经过
评审的策略变更才能登记具体组合；不接受未知许可证或 WITH 例外作为此字段的
快捷准入项，不提供来自目标仓库或命令行的临时放行参数。组合的 AND/OR 顺序及
冗余括号可规范化，但 AND 与 OR 不等价。

原 Copyright、SPDX、传统许可证正文独立保护。原表达式在 AND 组合中完整保留时，
不误报 Copyright 被删除；组合自身仍执行准入审核。删除 SPDX、替换许可证、
丢弃原 AND 项、增加 OR 选择或 WITH 例外不能仅因仍包含旧许可证名称就放行。
这不是法律兼容性或再许可授权判断。

## 验证要求

- 两个缺少子仓库对象的 Gitlink 更新不导致父仓库字段扫描 invalid。
- 新增/重命名 Gitlink、删除及普通文件互换覆盖真实 Git fixture。
- AITER 的 MIT 到 Apache-2.0 AND MIT 保留组合审批，不再报告 Copyright 删除。
- 明确批准组合的独立策略测试，以及 OR/WITH、未知项、非法表达式的负向测试。
- 删除 Copyright、SPDX 或许可证正文继续阻断。
- 全部原生自测、单元回归与 Runner 启动测试通过；外部扫描器验证单独披露。

参考：[Git 子模块](https://git-scm.com/docs/gitsubmodules)、
[SPDX 表达式](https://spdx.github.io/spdx-spec/v3.0.1/annexes/spdx-license-expressions/)。
