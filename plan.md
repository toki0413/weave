# Intuita × Tiny World Builder 全量借鉴实施计划

> 目标：将分析报告中识别的 10 个借鉴项全部实施到 Intuita 代码库。
> 策略：分 4 个阶段（P0 → P1 → P2 → P3），每阶段后运行 GdUnit4 测试（151 tests），确保零错误零失败。

---

## Phase 1：数据验证与存储（P0）

### 1.1 JSON Schema 验证体系
- **文件**：`data/levels/level.schema.json`
- **内容**：基于 world.schema.json 的结构，定义 Intuita 关卡数据的 JSON Schema Draft 2020-12
- **字段**：`v`（版本号）、`chapter`、`level`、`title`、`domain`、`construction_mode`、`elements`、`goals`、`constraints`、`fog_zones`、`lattice_parameters`、`lattice_angles`、`space_group_number`、`space_group_symbol`、`available_tools`、`journal_entry`、`hint`、`scale_label`、`scale_range`、`reward_cores`、`scene_config`
- **elements 定义**：`symbol`、`position`（Vector3 对象或 tuple）、`wyckoff_label`、`wyckoff_multiplicity`
- **goals 定义**：`type`（enum）、`description`、`element`、`wyckoff`、`required_count`、`max_deviation`、`required_layer`
- **version**：v=1，预留 future migration

### 1.2 运行时 Schema 验证
- **文件**：`scripts/autoload/level_data_validator.gd`
- **修改**：在 `validate()` 中增加 schema 版本检查（检查 `v` 字段），并定义 `validate_against_schema()` 方法
- **兼容**：不破坏现有验证逻辑，schema 验证作为补充层

### 1.3 静态 Schema 验证（Python）
- **文件**：`tools/level_solver.py`
- **修改**：
  - 导入 `jsonschema`（若未安装则 graceful fallback）
  - 在 `analyze_level()` 中先运行 `validate_level_against_schema(data)`
  - 验证失败时记录到 `notes` 中但不中断分析（backward compatible）
- **文件**：`tools/requirements.txt`（新增，记录 `jsonschema>=4.0`）

### 1.4 稀疏数据存储（Sparse Storage）
- **文件**：`data/levels/level_data.gd`
- **修改**：
  - 在 `to_json()` 中增加稀疏模式：如果 `elements` 数量 > 100，仅存储非默认元素（默认 = 空位/无原子）
  - 定义 `sparse_mode: bool = false`（默认关闭，小关卡不受影响）
  - 在 `from_json()` 中检测 `sparse_mode` 标志并解压
  - 新增 `to_compact()` / `from_compact()` 方法：将 `elements` 从对象数组转换为压缩 tuple 数组（如 `[x, y, z, symbol, wyckoff_label, wyckoff_multiplicity]`）
- **文件**：`data/levels/level_data_loader.gd`
  - 在 `load_level_data()` 中调用 `from_compact()` if needed
- **注意**：当前 45 关都是小关卡，稀疏模式默认 off。大晶胞关卡（如 20×20×20）可手动开启。

---

## Phase 2：视觉反馈与系统扩展（P1）

### 2.1 邻接感知渲染（Adjacency-Aware Rendering）
- **文件**：`scripts/construction/atom_node.gd`
- **新增方法**：`update_neighbor_visuals()`：检测邻近原子，如果符合成键距离则更新自身和邻居的键可视化
- **文件**：`scripts/construction/atom_placement_manager.gd`
- **修改**：在 `place_atom_at_marker()` 和 `restore_atom()` 中，放置完成后调用 `atom.update_neighbor_visuals()`
- **效果**：放置 Na 时，邻近的 Cl 自动高亮并显示键连接；键的视觉效果实时更新
- **边界**：不修改守恒矩阵逻辑（只改视觉），不破坏 `undo_redo`（undo 时移除键）

### 2.2 Settings 键值系统（分层命名空间）
- **文件**：`data/settings/settings_defaults.json`（新增）
- **内容**：
  ```json
  {
    "v": 1,
    "defaults": {
      "intuita:render:hdri_quality": "high",
      "intuita:audio:music_volume": 0.5,
      "intuita:audio:sfx_volume": 0.86,
      "intuita:game:show_tutorial": true,
      "intuita:game:language": "en",
      "intuita:render:atom_glow": true,
      "intuita:render:fog_density": 0.36
    }
  }
  ```
- **文件**：`scripts/autoload/settings_manager.gd`
- **修改**：
  - 在 `_ready()` 中从 `res://data/settings/settings_defaults.json` 加载默认值
  - 新增 `get_setting(key: String, default: Variant) -> Variant`（支持分层键如 `intuita:render:hdri_quality`）
  - 新增 `set_setting(key: String, value: Variant) -> void`
  - 保持现有 `load_settings()` / `save_settings()` 的兼容性（将旧格式迁移到键值格式）
  - 现有硬编码设置（如 `music_volume`）作为 `get_setting("intuita:audio:music_volume")` 的 shortcut
- **文件**：`data/settings/settings_migration.gd`（新增）
  - `migrate_v0_to_v1()`：将旧 `settings.tres` 中的字段映射到新键值格式

### 2.3 粒子氛围系统（Particle Atmosphere）
- **文件**：`scripts/effects/particle_system.gd`（新增）
- **内容**：
  - 使用 Godot `GPUParticles3D` 创建云、雪、雨、光晕等效果
  - `create_clouds()`：在场景上方生成粒子云，颜色由守恒矩阵状态决定（HEALTHY=白色，WARNING=灰色，CRITICAL=黑色，DISINTEGRATED=红色）
  - `create_precipitation(type: String, intensity: float)`：雨/雪
  - `create_validation_burst(position: Vector3)`：验证成功时的粒子爆发
- **文件**：`scripts/autoload/conservation_engine.gd`
- **修改**：在 `state_changed` 信号中增加 `emit("atmosphere_update", new_state)`，由 `particle_system.gd` 接收
- **文件**：`scripts/construction/construction_canvas.gd`
- **修改**：在 `_ready()` 中初始化 `particle_system.gd`，在 `_on_conservation_state_changed()` 中调用 `particle_system.update_atmosphere(state)`
- **测试**：新增 `scripts/tests/particle_system_test.gd`（至少 3 个测试：cloud_creation、state_color_change、validation_burst）

---

## Phase 3：高级功能（P2）

### 3.1 Voxel Stamp 系统（自定义 3D 对象）
- **文件**：`scripts/construction/voxel_stamp_renderer.gd`（新增）
- **内容**：
  - 将 `customParts` 数组（box/cylinder/sphere + material + size/pos）转换为 `ArrayMesh` 或 `MeshInstance3D`
  - 支持 `box`、`cylinder`、`sphere`、`cable`（线/绳）四种基本体
  - 与 `element_data_resource.gd` 配合：在 `element_data.gd` 中新增 `custom_shape` 字段
- **文件**：`data/elements/custom_shapes/`（新增目录）
  - `benzene.json`：苯环 = 6 个圆柱 + 1 个圆环
  - `graphene.json`：石墨烯片 = 蜂窝网格
- **文件**：`scripts/resources/element_data_resource.gd`
- **修改**：在 `_build_default_data()` 中为复杂元素（C、O 等）预留 `custom_shape` 字段
- **测试**：新增 `scripts/tests/voxel_stamp_test.gd`（至少 2 个测试：benzene_render、graphene_render）
- **注意**：此功能不强制启用，默认使用球体。在 `construction_canvas.gd` 的 `_create_atom_node()` 中检测 `elem.has("custom_shape")` 并分支。

### 3.2 AI 关卡生成集成
- **文件**：`tools/ai_level_generator.py`（新增）
- **内容**：
  - 使用 LLM API（OpenAI/Gemini，通过环境变量 `OPENAI_API_KEY` / `GEMINI_API_KEY`）
  - 输入：自然语言描述（如"设计一个关于 ZnS 闪锌矿的关卡，要求立方晶系，Wyckoff 位置填充"）
  - 输出：符合 `level.schema.json` 的 JSON 草稿
  - 验证：调用 `level_solver.py` 的 `analyze_level()` 检查守恒矩阵可解性
  - 如果不可解，自动调整 `max_deviation` 或 `required_count` 并重试
- **文件**：`tools/ai_level_generator_prompts.py`（新增）
  - 定义系统提示词和 few-shot 示例（NaCl、LiFePO4、CaTiO3）
- **文件**：`tools/ai_level_generator_cli.py`（新增）
  - 命令行入口：`python tools/ai_level_generator_cli.py --prompt "ZnS 闪锌矿" --output data/levels/json/chapter_5_level_1.json`
- **测试**：新增 `scripts/tests/ai_level_generator_test.gd`（离线模式：使用预生成 JSON 验证格式和可解性）
- **注意**：不引入运行时依赖。AI 生成是离线工具，运行时只使用生成的 JSON。

### 3.3 扩散模拟引擎（Diffusion Engine）
- **文件**：`scripts/simulation/diffusion_engine.gd`（新增）
- **内容**：
  - 在 "反应"（reaction）和 "设备"（device）域中运行
  - 简化版分子动力学：原子在晶格中按概率移动（Metropolis 算法或随机 walk）
  - 离子迁移：Li+ 在固态电解质中沿通道移动，遇到障碍物时重新寻路
  - 与 `ConservationEngine` 交互：每次移动触发 `apply_perturbation()`
  - 与 `FogSystem` 交互：在 "扩散方程" 关卡中，Fog 随浓度梯度变化
- **文件**：`scripts/simulation/pathfinder.gd`（新增）
  - A* 寻路，在晶格坐标（x, y, z）中移动，考虑障碍物（已占据的原子位置）
- **文件**：`scripts/tests/diffusion_engine_test.gd`（新增）
  - 测试：random_walk_does_not_crash、li_migration_reaches_target、pathfinder_avoids_obstacles
- **注意**：此功能仅在特定关卡（如 Ch2-L5 流体边界层、Ch3-L2 全固态电池）中启用。默认关闭。

---

## Phase 4：工程优化与交互（P3）

### 4.1 双格式数据表示（Compact Tuple）
- **文件**：`data/levels/level_data.gd`
- **新增方法**：
  - `to_compact_tuple() -> Array`：将 `elements` 从对象数组压缩为 tuple 数组 `[x, y, z, symbol, wyckoff_label, wyckoff_multiplicity]`
  - `from_compact_tuple(arr: Array) -> Array[Dictionary]`：解压为对象数组
  - `to_compact_goals() -> Array`：将 `goals` 压缩为 tuple `[type, element, wyckoff, required_count, max_deviation]`
  - `from_compact_goals(arr: Array) -> Array[Dictionary]`
- **文件**：`data/levels/json/` 下的现有 45 个 JSON 文件
- **操作**：不修改现有文件（保持对象格式）。新增关卡可使用 tuple 格式。
- **文件**：`scripts/autoload/level_data_loader.gd`
- **修改**：在 `load_level_data()` 中检测 `elements` 的格式（对象或 tuple），自动解压
- **注意**：此功能为网络传输优化（如未来 multiplayer），当前不影响单机运行时。

### 4.2 编号顺序引擎（Autoload Numbering）
- **文件**：`project.godot` 的 `autoload` 部分
- **操作**：为所有 autoload 脚本添加编号前缀，明确加载顺序：
  ```
  00_game_logger.gd
  01_error_handler.gd
  02_settings_manager.gd
  03_i18n_manager.gd
  04_achievement_manager.gd
  05_level_manager.gd
  06_sound_manager.gd
  07_conservation_engine.gd
  08_fog_system.gd
  09_tutorial_manager.gd
  10_proof_tree.gd
  11_morphism_system.gd
  12_verification_pipeline.gd
  13_leaderboard_manager.gd
  14_player_experience.gd
  ```
- **文件**：`scripts/autoload/` 目录下重命名文件
- **注意**：重命名文件后需要更新 `project.godot` 的 `autoload` 路径和 `class_name` 引用（如果有）。
- **风险**：`class_name` 与文件名无关，但 `preload("res://scripts/autoload/xxx.gd")` 需要更新路径。

### 4.3 拖放导入（Drag & Drop Import）
- **文件**：`scripts/construction/construction_canvas.gd`
- **修改**：
  - 在 `_input()` 中处理 `InputEventDropFiles`（Godot 4.2+ 支持文件拖放）
  - 如果文件是 `.json`：调用 `level_data_loader.load_level_data_from_path()` 加载为沙盒关卡
  - 如果文件是 `.tres`：调用 `element_data_resource.load_from_path()` 导入自定义元素数据
  - 如果文件是 `.png` / `.jpg`：作为 HDRI 背景替换（可选）
- **文件**：`scripts/autoload/level_data_loader.gd`
- **新增方法**：`load_level_data_from_path(path: String) -> LevelData`
- **测试**：新增 `scripts/tests/drag_drop_test.gd`（使用 `InputEventDropFiles` 模拟拖放）
- **注意**：`InputEventDropFiles` 在 headless 模式下可能不可用，测试需加 `if DisplayServer.has_feature(DisplayServer.FEATURE_DROP_FILES)` 保护。

---

## 验证与测试策略

每阶段完成后：
1. 运行 `GdUnit4` 全量测试：`151 tests | 0 errors | 0 failures`
2. 如果新增测试，确认新增测试通过
3. 如果修改 autoload 或核心模块，运行 `beginner_exploration_test` 和 `full_playthrough_test` 确认手动/全关卡通关正常
4. 运行 `level_solver.py` 确认 45 关可解性分析结果正确
5. 检查 `godot_err.txt` 是否有新增 warning/error

---

## 文件变更总览

| 新增文件 | 修改文件 | 删除文件 |
|---------|---------|---------|
| `data/levels/level.schema.json` | `data/levels/level_data.gd` | — |
| `data/settings/settings_defaults.json` | `scripts/autoload/level_data_validator.gd` | — |
| `data/settings/settings_migration.gd` | `scripts/autoload/settings_manager.gd` | — |
| `scripts/effects/particle_system.gd` | `scripts/autoload/conservation_engine.gd` | — |
| `scripts/construction/voxel_stamp_renderer.gd` | `scripts/construction/atom_node.gd` | — |
| `data/elements/custom_shapes/benzene.json` | `scripts/construction/atom_placement_manager.gd` | — |
| `data/elements/custom_shapes/graphene.json` | `scripts/construction/construction_canvas.gd` | — |
| `tools/ai_level_generator.py` | `scripts/resources/element_data_resource.gd` | — |
| `tools/ai_level_generator_prompts.py` | `scripts/autoload/level_data_loader.gd` | — |
| `tools/ai_level_generator_cli.py` | `project.godot` | — |
| `tools/requirements.txt` | `tools/level_solver.py` | — |
| `scripts/simulation/diffusion_engine.gd` | — | — |
| `scripts/simulation/pathfinder.gd` | — | — |
| `scripts/tests/particle_system_test.gd` | — | — |
| `scripts/tests/voxel_stamp_test.gd` | — | — |
| `scripts/tests/ai_level_generator_test.gd` | — | — |
| `scripts/tests/diffusion_engine_test.gd` | — | — |
| `scripts/tests/drag_drop_test.gd` | — | — |

---

## 实施顺序

1. **Phase 1**（P0）：JSON Schema + 稀疏存储 → 运行测试 → 确认通过
2. **Phase 2**（P1）：邻接渲染 + Settings + 粒子氛围 → 运行测试 → 确认通过
3. **Phase 3**（P2）：Voxel Stamp + AI 生成 + 扩散模拟 → 运行测试 → 确认通过
4. **Phase 4**（P3）：双格式 + 编号引擎 + 拖放导入 → 运行测试 → 确认通过
5. **最终验证**：全量 151 测试通过，level_solver.py 45 关分析正确，无新增错误日志
