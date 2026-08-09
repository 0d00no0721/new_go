# 围棋新规则探索

本仓库是围棋新规则变体的探索工作区。每个子目录是一个独立方向，含自己的规则文档、实现与测试。

## 方向

| 目录 | 方向 | 说明 |
|------|------|------|
| [`ban-selection/`](./ban-selection/) | Ban 选围棋 | 在 KataGo v1.16.4 上实现 20 路 Ban 选围棋变体（Ban 选阶段 10 禁点 + 正式对局黑贴 4.25 子），含 CLI/GUI 对弈工具 + 静态官网。详见 [`ban-selection/README.md`](./ban-selection/README.md)。 |
| _（待补充）_ | _下一个方向_ | _预留_ |

## 仓库

- GitHub: https://github.com/0d00no0721/new_go
- 在线对弈（Ban 选）: https://0d00no0721.github.io/new_go/play.html

## 目录结构

```
new_go/
├── README.md                 # 本文件（父级导航）
├── AGENTS.md                 # 父级 agent 指引
├── .gitignore
└── ban-selection/            # 方向一：Ban 选围棋
    ├── README.md             # 方向详情
    ├── AGENTS.md             # 方向 agent 指引
    ├── *.py                  # 源码 + 测试
    ├── website/              # 静态官网（GitHub Pages 部署）
    ├── katago-src/           # KataGo 改造源码（gitignored）
    └── dist_opencl/          # 编译产物（gitignored）
```
