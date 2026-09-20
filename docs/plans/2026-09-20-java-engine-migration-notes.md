# Java 引擎迁移参考笔记

日期：2026-09-20
来源：对 `https://github.com/pengjiu/ChineseChess`（本地克隆 `/tmp/opencode/ChineseChess/`，如不存在执行 `git clone https://github.com/pengjiu/ChineseChess.git /tmp/opencode/ChineseChess`）的完整架构分析报告。

> 本笔记供 `docs/plans/2026-09-20-ai-engine-implementation.md` 实现计划使用。分析报告中的行号均指
> `/tmp/opencode/ChineseChess/com/pj/chess/**/*.java`。

## 关键常量补充（已对照源码 `ChessConstant.java` 二次核验）

- 棋子基础类型：`KING=7, CHARIOT=6, KNIGHT=5, GUN=4, ELEPHANT=3, GUARD=2, SOLDIER=1`
- 角色（chessRoles）：**红方角色 = 1..7（红兵=1…红帅=7）**，**黑方角色 = 8..14（黑卒=8…黑将=14）**（即黑 = 类型 + 7）
- 棋子索引（allChess/board 所用）：
  - 16-31 黑方，顺序：16=黑将, 17-18=黑车, 19-20=黑马, 21-22=黑炮, 23-24=黑象, 25-26=黑士, 27-31=黑卒
  - 32-47 红方，顺序：32=红帅, 33-34=红车, 35-36=红马, 37-38=红炮, 39-40=红相, 41-42=红仕, 43-47=红兵
- `chessPlay = {16, 32}`：索引 0=黑方起点、1=红方起点；`REDPLAYSIGN=1`、`BLACKPLAYSIGN=0`
- 空位：`NOTHING = -1`（board 与 allChess 的空值）
- `boardRow[site] = site // 9`、`boardCol[site] = site % 9`
- `indexOfAttackAndDefense[role]`（roles 1..14）：`[_,0,1,1,0,0,0,1, 0,1,1,0,0,0,1]`
  → 攻击子 = 车(6/13)、马(5/12)、炮(4/11)、兵(1/8)；防御子 = 士(2/9)、象(3/10)、将(7/14)
- `maxScore=9999`、`LONGCHECKSCORE=8888`、`drawScore=0`、`MAXDEPTH=6`（默认难度）
- 90 位棋盘 `site = row*9+col`，row=0 为黑方底线、row=9 为红方底线（**与 chess_engine 的 y 相反：row = 9 - y**）
- 预生成表尺寸清单：`KnightBitBoards[90]`、`KnightLegBitBoards[90]`、`KingCheckedSoldierBitBoards[90]`、
  `KnightBitBoardOfAttackLimit[90][200]`、`ElephanLegBitBoards[90]`、`ElephanBitBoardOfAttackLimit[90][200]`、
  `ChariotBitBoardOfAttackRow[90][512]`、`ChariotBitBoardOfAttackCol[90][1024]`、
  `MoveChariotOrGunBitBoardRow[90][512]`、`MoveChariotOrGunBitBoardCol[90][1024]`、
  `GunBitBoardOfAttackRow[90][512]`、`GunBitBoardOfAttackCol[90][1024]`、
  `GunBitBoardOfFakeAttackRow[90][512]`、`GunBitBoardOfFakeAttackCol[90][1024]`、
  `GunBitBoardOfMoreRestAttackRow[90][512]`、`GunBitBoardOfMoreRestAttackCol[90][1024]`、
  `KingBitBoard[90]`、`GuardBitBoard[90]`、`SoldiersBitBoard[2][90]`、`MaskChesses[90]`、
  `ChariotAndGunMobilityRow[90][512]`、`ChariotAndGunMobilityCol[90][1024]`、`KnightMobility[90][200]`
- `boardMap[256]`：16×16 辅助坐标（行 3..12、列 3..11）→ 90 坐标，`site = (r-3)*9 + (c-3)`
- `Tools.exchange`（红黑镜像）在 90 坐标下等价于 `(row,col) → (9-row,col)`，即 `site → 81 - 9*(site//9) + site%9`

---
<task id="ses_f40a9ffadffe72ynq3ucZMhRWC" state="completed">
<task_result>
所有源码文件已完整读取并交叉验证完毕。以下是详尽的架构分析报告。

---

# ChineseChess Java 引擎完整架构分析报告

代码总量 9832 行 / 25 个文件。所有中文注释在原文件中为 GBK 乱码，以下分析中的语义描述由代码逻辑反推。

---

## 1. 整体架构与依赖关系

### 1.1 包结构

```
com/pj/chess/
├── ChessConstant.java          (163行) 常量 + 全部全局预生成表声明
├── BitBoard.java               (178行) 4×int 位棋盘
├── ChessInitialize.java        (883行) 所有走法/攻击/掩码表的初始化
├── ChessParam.java             (203行) 局面状态容器（chessparam包）
├── Tools.java                  (350行) FEN解析、棋色镜像、存档（工具+UI混合）
├── NodeLink.java               (114行) 搜索/PV双向链节点
├── ComputerLevel.java          ( 22行) 难度枚举（深度+时限）
├── AICoreHandler.java          (192行) AI调度、计时器、阶段选择、动态子力价值
├── ChessBoardMain.java         (802行) Swing UI + 引擎粘合层（入口）
├── chessmove/
│   ├── ChessMoveAbs.java       (723行) 抽象基类：位棋盘着法生成+合法性+将军检测
│   ├── ChessMovePlay.java      ( 93行) 主搜索着法分类（MVV-LVA/历史）
│   ├── ChessQuiescMove.java    ( 81行) 静态搜索着法分类
│   ├── MoveNode.java           ( 49行) 着法对象（无int压缩）
│   └── MoveNodesSort.java      (237行) 着法排序状态机
├── movelist/
│   └── MoveNodeList.java       ( 83行) 定容着法数组（无越界检查）
├── searchengine/
│   ├── SearchEngine.java       (333行) 抽象搜索基类：quiesc、长将、和棋、空着R
│   └── PrincipalVariation.java (355行) 唯一实际搜索实现（PVS+ID）
├── evaluate/
│   ├── EvaluateCompute.java    (516行) 抽象基类：子力价值、分区表、炮检测
│   ├── EvaluateComputeMiddle.java (373行) 废弃（evaluate 提前return）
│   ├── EvaluateComputeOther.java  (290行) 废弃（evaluate 提前return）
│   ├── EvaluateComputeMiddleGame.java (348行) 【实际启用】中局评估
│   └── EvaluateComputeEndGame.java    (220行) 【实际启用】残局评估
├── history/
│   └── CHistoryHeuritic.java   ( 43行) 历史启发表
└── zobrist/
    ├── TranspositionTable.java (433行) 置换表（2层/槽）+ Zobrist 增量
    ├── HashItem.java           ( 39行) 置换表条目
    └── InitZobristList32And64.java (2709行) 纯随机数常量表
```

### 1.2 依赖与调用关系

```
ChessBoardMain (入口 main L757, UI+引擎混合)
  ├─ initHandler() L94-122: FEN → Tools.parseFEN → ChessInitialize.getGlobalChessParam
  │                          → new TranspositionTable() → new NodeLink
  │                          → new ChessMovePlay(cmp) 用于 UI 走子
  ├─ mousePressed L441-476 → cmp.legalMove → showMoveNode → cmp.moveOperate
  └─ computeThink L655 → AICoreHandler.setLocalVariable → launchTimer → run
        └─ searchEngineFactory L78 → new PrincipalVariation(chessParam副本, Evaluate, TT, NodeLink)
              └─ SearchEngine 构造 L60 → initChessSiteScore(L69) → getChessBaseScore(L74)
                    └─ PrincipalVariation.searchMove L40
                          ├─ MoveNodesSort → ChessMovePlay → ChessMoveAbs
                          ├─ rootNegaScout/negaScout
                          └─ quiescSearch → ChessQuiescMove
```

关键依赖规则：
- `ChessMoveAbs/Play/Quiesc` 共同持有 `ChessParam`、`TranspositionTable`、`EvaluateCompute` 三个引用（构造函数 L32-58 ChessMovePlay）。
- `SearchEngine` 持有 `ChessMovePlay`、`ChessQuiescMove`、`EvaluateCompute`、`TranspositionTable`、`NodeLink`（root PV 链）。
- `EvaluateCompute` 只依赖 `ChessParam` 和全局预生成表。
- 全局静态状态贯穿全程序：`ChessConstant` 的 20+ 张表、`EvaluateCompute.chessBaseScore`、`CHistoryHeuritic.cHistory`、`TranspositionTable.tranZobrist/fenLib/boardZobristStatic32/64`。

### 1.3 UI 剥离清单

**必须剥离（纯 Swing/AWT）**：
- `ChessBoardMain` 中的：JFrame/JPanel/JLabel/Button/JMenu/JRadioButtonMenuItem/JCheckBoxMenuItem/JOptionPane/ButtonGroup/GridLayout/BorderLayout/Dimension
- `ButtonActionListener`（ActionListener+WindowListener+MouseListener，L331-482）
- `MenuItemActionListener`（L545-602）
- `SoundEffect`（Applet/AudioPlayer，L773-802）
- `getImageIcon`/`setBoardIcon*`/`setCenter`（图片渲染，L124-182, L290-309）
- `readSaved`/`gameOverMsg`（文件对话框，L483-491, L712-756）

**可保留/需移植的引擎粘合逻辑**（在 UI 中但属于引擎职责）：
- `initHandler` L94-122：局面初始化、走子历史根节点
- `move`/`showMoveNode` L322-330/L696-702：应用着法 + 同步 Zobrist 静态值（`transTable.synchroZobristBoardToStatic()`）
- `mousePressed` 中的选子/合法性检查/放下
- `computeThink`/`computeThinkStart`/`computeAIMoving`/`backstageThink`：AI 调度
- `checkGameOver` L499-544：终局判定（吃将、长将、300回合、无攻击子）

**核心引擎（与 UI 完全无关）**：
`BitBoard, ChessConstant, ChessInitialize, ChessParam, ChessMove*, MoveNodesSort, MoveNodeList, SearchEngine, PrincipalVariation, EvaluateCompute*, CHistoryHeuritic, TranspositionTable, HashItem, NodeLink, ComputerLevel, AICoreHandler(逻辑部分), Tools(parseFEN/exchange/getBoradSite)`。

`AICoreHandler` 属于"引擎外壳"：不依赖 Swing，只依赖 Timer/线程。

---

## 2. 棋盘表示

### 2.1 坐标与索引

- **90 格棋格索引**：`site = row*9 + col`，`row∈[0,9]`，`col∈[0,8]`。row=0 是黑方底线，row=9 是红方底线（`ChessConstant.boardRow/boardCol` L68-94）。
- 另有一套 16×16 的坐标仅用于初始化预生成表：`boardMap[256]` 把行 3..12、列 3..11 映射到 0..89（L131-148）；`Tools.isBoardTo255` L126-133 判断合法区。

### 2.2 棋盘数组

`ChessParam`（`chessparam/ChessParam.java`）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `board[90]` | site→棋子索引 | 0-15 保留，16-31 黑，32-47 红；空位 `NOTHING=-1` |
| `allChess[48]` | 棋子索引→site | 反向索引；`-1` 表示已被吃 |
| `baseScore[2]` | 双方"子力+位置"分缓存 | 搜前由 `SearchEngine.getChessBaseScore()` 全量重算，之后增量维护 |
| `boardBitRow[10]` | 每行占用 | `bit(8-col)`，即 col0→bit8，col8→bit0 |
| `boardBitCol[9]` | 每列占用 | `bit(9-row)`，即 row0→bit9，row9→bit0 |
| `boardRemainChess[15]` | 各角色剩余数 | 索引 1-7 红、8-14 黑 |
| `attackAndDefenseChesses[2][2]` | [方][攻击/防御子数] | `indexOfAttackAndDefense` L44-47 把角色映射到 0=攻击(车马炮兵)或 1=防御(士象将) |
| `maskBoardChesses` | BitBoard | 全体棋子 |
| `maskBoardPersonalChesses[2]` | 每方全部棋子 | 索引 REDPLAYSIGN=1 / BLACKPLAYSIGN=0 |
| `maskBoardPersonalRoleChesses[15]` | 每角色棋子 | 1-7 红、8-14 黑，0 不用 |

**棋子编码**（`ChessConstant` L8-31）：

```
类型:  SOLDIER=1, GUARD=2, ELEPHANT=3, GUN=4, KNIGHT=5, CHARIOT=6, KING=7
红:    1..7        (REDSOLDIER..REDKING)
黑:    8..14       (BLACKSOLDIER..BLACKKING = 类型+7)
棋子索引 16-31=黑方（按 k,r,r,n,n,c,c,b,b,a,a,p,p,p,p,p），32-47=红方
chessRoles[48]       棋子索引→角色(1-14)
chessRoles_eight[48] 棋子索引→基础类型(1-7)，用于历史表第一维
chessPlay[]={16,32}  黑方/红方棋子索引起点（索引0=黑、1=红）
```

### 2.3 BitBoard 位棋盘（`BitBoard.java`）

**90 位 = 4 个 int**（L7, L67-77）：

```java
Low  : bits 0-26   → site 0..26   (row 0-2)
Mid1 : bits 0-26   → site 27..53  (row 3-5)   bit = site-27
Mid2 : bits 0-26   → site 54..80  (row 6-8)   bit = site-54
Hi   : bits 0-8    → site 81..89  (row 9)     bit = site-81
```

即按"每 3 行一个 32 位字"切分，最后一个字只用 9 位。`BitBoard(int site)` 生成单格掩码；`BitBoard(int[] board)` 对非零元素 XOR 生成（L9-15）——注意 `MaskChesses[i]` 的定义，这也说明 board 数组允许用 0 或 -1 表示空（空位不异或）。

**红黑不分开**：BitBoard 本身颜色无关；颜色信息通过 `maskBoardPersonalChesses[play]` 与 `maskBoardPersonalRoleChesses[role]` 两张掩码表体现。

核心操作：`assignAnd/Or/Xor`（原地）、`assignAndToNew/OrToNew/XorToNew`（新对象，注意返回的是 `Arg XOR/AND/OR Arg1`，第一个参数是操作数、第二个是副本基底）；`isEmpty`；`Count`（SWAR popcount L128-138）；`checkSumOfKnight/Elephant`（腿位折叠哈希，见 3.3）；`MSB(play)`（L100-125）。

**MSB 是名字误导**：内部 `Msb32` 用 `Integer.numberOfTrailingZeros`（最低置位）。扫描顺序：

- 红方 `REDPLAYSIGN`：Low→Mid1→Mid2→Hi，字内低位到高位 ⇒ **site 升序 0,1,2,…,89**
- 黑方 `BLACKPLAYSIGN`：Hi→Mid2→Mid1→Low，字内低位到高位 ⇒ **site 顺序 81..89, 54..80, 27..53, 0..26**

由于着法列表按 `MSB` 循环生成，这一顺序决定了同分行棋的生成次序（Python 复刻须保留）。

### 2.4 静态初始化

`ChessInitialize` 的第 96-102 行静态块：先构造 `MaskChesses[90]`，然后 `new ChessInitialize()` 触发全部表构建。过程（L103-156）：

1. `initKnightMove` L214-245（马走法+腿位）
2. `initElephantMove` L249-290（象走法+腿位，按 16×16 行限制方向实现"象不过河"）
3. `initSoldier` L294-331（兵卒走法，过河与否三方向/一方向）
4. `initChariotGunVariedMove` ×8（车/炮的行列攻击表、平移表、伪攻击表、隔两子攻击表）
5. `initGunFackEatMove` ×2（炮的压制位）
6. `preAllBitBoard` L158-198（生成全部 BitBoard 表和机动性计数表）

---

## 3. 着法生成

### 3.1 着法对象：没有 int 编码

`MoveNode`（`MoveNode.java` L13-49）就是 5 个 public int 字段的对象：

```java
public int destChess, srcChess, srcSite, destSite, score;
public boolean isOppProtect;
```

**没有把着法压缩为 int**（用户问题 3 的答案：不存在 int 编码格式）。`score` 在生成时是排序键，在根搜索后被覆写为该着法的搜索结果值。`equals` 只比较 srcSite/destSite（L44-48）。

### 3.2 生成入口

`ChessMoveAbs` 提供两套生成函数：

```java
genEatMoveList(int play)   // L452-462：先遍历 chessPlay[play]+1 .. +15（跳过将），最后生成将的吃子
genNopMoveList(int play)   // L471-481：同样的迭代顺序
```

每个棋子按角色分派到 `chessEatMove`（L574-635）或 `chessNopMove`（L636-704）。两者结构一致：

1. 根据角色取该棋子的**攻击位棋盘**（吃子）或**平移位棋盘**（非吃子），与合法区域掩码求交；
2. `while((destSite=bitBoard.MSB(play))!=-1) { savePlayChess(src,dest,play); bitBoard.assignXor(MaskChesses[destSite]); }`

取表逻辑逐角色（以 `chessEatMove` 为例）：

| 角色 | 吃子着法来源 | 非吃子着法来源 |
|---|---|---|
| 车 | `ChariotBitBoardOfAttackRow[site][row] XOR Col[site][col]` ∩ 对方棋子 | `MoveChariotOrGunBitBoardRow[site][row] XOR Col[...]` |
| 马 | `KnightBitBoardOfAttackLimit[site][legKey]` ∩ 对方棋子，`legKey = (KnightLegBitBoards[site] ∩ 全体棋子).checkSumOfKnight()` | 攻击表 ∩ 全体棋子，再 `XOR` 攻击表（=攻击表∩空格） |
| 炮 | `GunBitBoardOfAttackRow[site][row] XOR Col[...]` ∩ 对方棋子 | 同车的平移表 |
| 象 | `ElephanBitBoardOfAttackLimit[site][legKey]` ∩ 对方棋子 | 攻击表 ∩ 全体棋子再 XOR |
| 将 | `KingBitBoard[site]` ∩ 对方棋子 | `KingBitBoard ∩ 全体` XOR `KingBitBoard` |
| 士 | `GuardBitBoard[site]` ∩ 对方棋子 | 同上模式 |
| 兵 | `SoldiersBitBoard[play][site]` ∩ 对方棋子 | ∩ 全体再 XOR |

注意：`assignXorToNew(A,B)` 返回 `B XOR A`，行/列两张表互不相交，XOR 等价并集。

### 3.3 预生成位掩码表清单

`ChessConstant` L105-129 声明（全部由 `ChessInitialize` 填充）：

| 表 | 维度 | 语义与索引约定 |
|---|---|---|
| `KnightBitBoards[site]` | [90] | 马的目标格集合（不考虑蹩腿） |
| `KnightLegBitBoards[site]` | [90] | 马腿位集合（去重后最多 4 个不同正交格） |
| `KnightBitBoardOfAttackLimit[site][key]` | [90][200] | 给定马腿状态 `key` 时的合法攻击位；`key` 由腿位位棋盘的折叠校验和得到 |
| `KnightMobility[site][key]` | [90][200] | 上表的 Count()（机动性） |
| `KingCheckedSoldierBitBoards[site]` | [90] | 能攻击到 site 的兵/卒位置（用于将军检测） |
| `ElephanLegBitBoards[site]` | [90] | 象眼位集合 |
| `ElephanBitBoardOfAttackLimit[site][key]` | [90][200] | 象腿状态→合法攻击位 |
| `ChariotBitBoardOfAttackRow[site][rowMask]` | [90][512] | 车在该行列方向的**吃子落点**：沿行两方向各遇到**第一个阻挡格**即停 |
| `ChariotBitBoardOfAttackCol[site][colMask]` | [90][1024] | 同上，列方向 |
| `MoveChariotOrGunBitBoardRow/Col` | [90][512]/[90][1024] | 车/炮的**平移落点**：所有空格，遇第一个阻挡停（不含阻挡格） |
| `GunBitBoardOfAttackRow/Col` | 同上 | 炮的**吃子落点**：跳过第一个阻挡（炮架），落点在第二个阻挡 |
| `GunBitBoardOfFakeAttackRow/Col` | 同上 | 炮的**压制位**：炮架之后的空位（到第二个棋子之前） |
| `GunBitBoardOfMoreRestAttackRow/Col` | 同上 | 隔**两个**棋子的吃子落点（重炮/叠炮检测） |
| `KingBitBoard[site]` | [90] | 将/帅九宫内一步（硬编码 L647-714） |
| `GuardBitBoard[site]` | [90] | 士/仕九宫内斜进一步（硬编码 L721-764） |
| `SoldiersBitBoard[2][site]` | [2][90] | 兵/卒走法，[play]=走子方 |
| `MaskChesses[site]` | [90] | 单格掩码 |
| `ChariotAndGunMobilityRow/Col` | [90][512]/[90][1024] | 车/炮的行/列空格数（平移位 Count） |

**行/列表的索引含义**（关键，容易看错）：
- `ChariotBitBoardOfAttackRow[site][j]` 的 `j` 是 `boardBitRow[行]` 原始 int（bit(8-col) 编码）。`initChariotGunVariedMove`（L343-417）以 bit 索引 `i` 找到车列 `num-i`，因此表的第一维实际是**车所在列 col**（0-8），不是棋盘行号。
- 列表第二维同理是 `boardBitCol`（bit(9-row)），第一维是**车所在行 row**（0-9），所以行组 9、列组 10。

`preGunAndChariotBitBoardAttack`（L610-640）负责把"行列局部表"展开为 90 坐标的 BitBoard：

```java
if(type==0) { rowOrCol=row; moveSiteTemp=moveSite[col]; site = 目标列号 + row*9; }
else        { rowOrCol=col; moveSiteTemp=moveSite[row]; site = 目标行*9 + col; }
```

**马/象的腿位折叠键**（L83-94）：

```java
checkSumOfKnight: temp1 = Low^Mid1^Mid2^Hi;
    r = (temp1&0x7f) + ((temp1>>>6)&0x7f) + ((temp1>>>13)&0x7f) + ((temp1>>>19)&0x7f);
checkSumOfElephant 同上但移位 0/7/14/21
```

我用脚本模拟了全部 90 个站点：马的 key 最大 **149**，象 key 最大 **149**，都小于表维度 200，因此原表不会越界（这是几何约束导致的，不是巧合可以忽略的）。Python 复刻可以保留 200 大小或放大到 512，但**键的计算公式必须完全一致**，否则查表结果不同。

`preBitBoardAttack`（L461-519）的生成算法：对某站点 i，取其腿位（去重）的所有非空子集（`getAllLegCombByLeg` L544-564 + `computCombination` L572-586），对每个子集构造"这些腿位被占据"的腿位位棋盘 `siteLegBit`，其折叠键即查表键；然后遍历该站点的 8 个（象 4 个）走法，腿位不在子集里的走法目标并入 `siteAttBit`。注意存在键碰撞时**后写覆盖**，复刻时保持覆盖语义即可。

**`KingCheckedSoldierBitBoards`**（L199-210）：从 `KnightLegBitBoards[i]`（4 个正交邻居）出发；若该站点有 4 个腿位（90 坐标中 30 个中央站点，我验证过列表），则 `i<45`（上半区，黑将九宫）去掉 `i-9`（上方），否则去掉 `i+9`（下方）。剩余 3 格恰好是"能吃到该格的兵位置"（正前 + 左 + 右）。

### 3.4 着法分类（排序键）

`ChessMovePlay.savePlayChess`（L44-83）与 `ChessQuiescMove.savePlayChess`（L44-64）决定一个着法进 `goodMoveList`（吃子优先列表）还是 `generalMoveList`：

**ChessMovePlay（主搜索）**：

```java
// 去重：若与已返回的 TT/killer 着法重复（存在 repeatMoveList），从表中置 null 并丢弃 L51-57
boolean isOppProtect = !(oppAttackSite & MaskChesses[destSite]).isEmpty(); // 目标格是否被对手攻击 L61
if (destChess != NOTHING) {
    int srcScore = isOppProtect ? 被吃子价值+位置分 : -500;      // L64-70
    int destScore = 吃子价值+位置分;                              // L71
    if (destScore >= srcScore) {                                 // L72
        new MoveNode(src,dest,srcChess,destChess,destScore-srcScore) → goodMoveList;
        return;
    }
}
new MoveNode(..., CHistoryHeuritic.cHistory[type(srcChess)][destSite] + (isOppProtect?0:256))
    → generalMoveList;                                            // L80-82
```

即：被吃子有保护时按 MVV-LVA（被吃值-吃子值）排序；无保护时 `srcScore=-500` 保证任何吃子都进 goodMoveList 且分数越高越好；非吃子按历史表（被保护的目标 +0，未被保护 +256）。

**ChessQuiescMove（静态搜索）**：只有 `被吃子价值+位置分 >= 150` 的吃子才进 goodMoveList（L52），其余（含普通吃子和所有非吃子）进 generalMoveList，score=历史表（L62）。注意静态搜索**不计算 oppAttackSite**（字段为 null，但该子类不访问它）。

### 3.5 合法性判断与将军检测

- `legalMove(play, moveNode)`（L226-302）：用于校验 TT/killer 着法。检查源子属于己方、目标不是己方子、`srcChess/destChess` 与当前棋盘一致，然后用与生成同样的查表逻辑确认目标在攻击位集合内。
- `checked(play)`（L312-370）：判断 play 方是否被将。依次检查：
  1. 对方车：`(ChariotBitBoardOfAttackRow[kingSite][row] XOR Col[kingSite][col]) ∩ 对方车位` 非空（L324-328）
  2. **飞将**：`ChariotBitBoardOfAttackCol[kingSite][col] ∩ MaskChesses[对方将位置]` 非空（L330-332）
  3. 对方炮：`GunBitBoardOfAttackRow/Col` 并集 ∩ 对方炮（L335-339）
  4. 对方马：先用 `KnightBitBoards[kingSite]` 筛出能攻击到将的马（技巧：马的攻击位集合对称，故"马能攻击将"⇔"将在马攻击位表中"），再对最多两匹马逐一验腿（L342-363）
  5. 兵：`KingCheckedSoldierBitBoards[kingSite] ∩ 对方兵位`（L365-367）
- `chkNum(play)`（L378-432）是"统计将军数"的死代码，全项目未调用（grep 验证）。

---

## 4. 搜索算法（PrincipalVariation / SearchEngine）

### 4.1 总体结构

- `SearchEngine`（抽象，实现 Runnable）提供：`quiescSearch`、`isLongChk`、`isDraw`、`isDanger`、`RAdapt`、`fineEvaluate`、`roughEvaluate`、`getChessBaseScore`、`setStretchNeedNumByDepth`。
- `PrincipalVariation` 是唯一具体引擎（`MDFSearchEngine` 只存在于注释中），实现 `searchMove`（迭代加深根搜索）、`rootNegaScout`（根 PVS）、`negaScout`（内部 PVS）。
- 上层由 `AICoreHandler.run`（L42-65）调用：`mtdfV = seEngine.searchMove(-maxScore, maxScore, depth)`，根分数存于 `mtdfV`，着法链由 `moveHistory.getNextLink()` 读取。

### 4.2 迭代加深与根搜索（searchMove L40-94）

```java
moveHistory.depth = 0;
setStretchNeedNumByDepth(depth);          // 15/19/23，但 StretchNeedNum 实际未被使用（死字段）
MoveNodesSort sort = new MoveNodesSort(swapPlay(moveHistory.play), new MoveNodeList(2), killerMove[depth], chessMove, false);
MoveNodeList moveNodeList = new MoveNodeList(100);
while ((moveNode = sort.next()) != null && !sort.isOver()) {   // 枚举根节点全部合法着法
    chessMove.moveOperate(moveNode);
    if (!chessMove.checked(currPlay)) { moveNode.score = initScore--; moveNodeList.add(moveNode); } // 100,99,98...
    chessMove.unMoveOperate(moveNode);
}
for (int d = 4; d <= depth && !isStop; d++) {                  // 固定从 4 层开始
    s = rootNegaScout(alpha, beta, d, moveNodeList, moveHistory);
    // 把本轮 PV 链上的着法写入 killerMove[d+1], killerMove[d], ...
    NodeLink nextLink = moveHistory.getNextLink(); int k = d + 1;
    while (nextLink != null && k >= 0) { killerMove[k][1]=killerMove[k][0]; killerMove[k][0]=nextLink.getMoveNode(); k--; nextLink=nextLink.getNextLink(); }
}
return s;
```

重要性质：
- 迭代**固定从 d=4 开始**，每次 +1 到难度 depth；`alpha/beta` 每轮都用调用方传入的 `-maxScore/+maxScore`（rootNegaScout 只用局部变量 `thisAlpha`，不回写）。
- 根着法列表**只枚举一次**，且排除了走完后被将军的着法；每轮搜索后 `moveNode.score` 被覆写为该着法结果（`rootNegaScout` L126），下一轮 `getSortAfterBestMove`（L215-228 选择排序）按上一轮结果降序选取，形成 PV-first。
- killer 表被**轮间 PV 路径**填充（不是仅在 beta 截断时）。
- depth<4 时返回 0。

### 4.3 根节点搜索 rootNegaScout（L95-148）

标准 PVS：

```java
isChecked = chessMove.checked(play); lastLink.chk = isChecked;
while (i < moveNodeList.size) {
    moveNode = getSortAfterBestMove(moveNodeList, i++);
    moveOperate;
    nodeLinkTemp = new NodeLink(play, moveNode, zob32, zob64); nodeLinkTemp.setLastLink(lastLink);
    if (isMove) {
        thisValue = -negaScout(-thisAlpha-1, -thisAlpha, depth-1, nodeLinkTemp, false);  // 零窗口
        if (thisValue > thisAlpha) thisValue = -negaScout(-beta, -thisAlpha, depth-1, nodeLinkTemp, true); // 重搜
    } else {
        thisValue = -negaScout(-beta, -thisAlpha, depth-1, nodeLinkTemp, true); // 首着全窗口
        isMove = true;
    }
    unMoveOperate; moveNode.score = thisValue;
    if (thisValue > bestValue) { bestValue = thisValue; bestNodeLink = nodeLinkTemp; if (thisValue > thisAlpha) thisAlpha = thisValue; }
    if (isStop) break;
}
if (isMove) { lastLink.setNextLink(bestNodeLink); return bestValue; }
else return -(maxScore - lastLink.depth);      // 无着法 = 被将死
```

注意根节点**没有 beta 截断直接返回**，它继续遍历全部根着法（这是为了让每个根着法都能获得分数用于排序）。

### 4.4 内部节点 negaScout（L154-337）按执行顺序

1. **王被吃**（L158-160）：`allChess[chessPlay[play]]==NOTHING` → `-(maxScore - lastLink.depth)`。
2. **深度下界保护**（L161-162）：`bestValue = lastLink.depth - maxScore`；若 `> beta` 立即返回（防止返回低于将死分数的值）。
3. **置换表探测**（L164-169）：`getTranZobrist(alpha,beta,depth,play,tranGodMoveNode,value)`，命中即返回；同时得到 TT 着法（`tranGodMoveNode`，容量 2）。
4. **被将检测**（L171-173）：`checked(play)` 并写入 `lastLink.chk`。
5. **长将检测**（L175-177）：`isLongChk(lastLink)` 为真 → `LONGCHECKSCORE`（8888）。
6. **和棋检测**（L178-183）：上一步是吃子且 `isDraw(lastLink)`（双方攻击子为 0）→ `drawScore`（0）。
7. **将军延伸**（L185-188）：`if (isChecked) depth++`（延伸到被将局面结束）。
8. **静态搜索入口**（L192-196）：`depth <= stopDepth`（`stopDepth` 初始恒为 0，从未被修改）→ `quiescSearch`。
9. **空着裁剪 + 验证**（L201-222）：
   ```java
   if (!lastLink.isNullMove && !isChecked && !isPVNode && depth>=2) {
       R = RAdapt(depth);                       // depth<=6→2, <=8→3, else 4
       if (chessParam.getAttackChessesNum(play) > 0) {   // 己方仍有攻击子
           val = -negaScout(-beta, -beta+1, depth-R-1, nullNode, false);
           if (val >= beta) {
               if (attackChessNum > 2 && depth < 6) return val;          // 弱验证
               val = -negaScout(-beta, -beta+1, depth-R+1, nullNode, false); // 加深验证
               if (val >= beta) return val;
           }
       }
   }
   ```
   注意空着节点是 `new NodeLink(play, true, zob32, zob64)`（`isNullMove=true`，`getMoveNode()==null`），并且空着搜索传入 `isPVNode=false`。
10. **内部迭代加深 IID**（L224-230）：`depth>=6 && isPVNode && TT着法为空` 时先以 `depth-2` 搜一次，把 PV 首着写入 `tranGodMoveNode` 和置换表根槽（`setRootTranZobrist`）。
11. **着法循环**（L231-315）：
    - 构造 `MoveNodesSort(play, tranGodMoveNode, killerMove[depth], chessMove, isChecked)`；
    - `movesSearchedCount = isPVNode ? 10 : 5`；
    - 每个着法先 `moveOperate`，若走完自己被将则 `unMoveOperate + continue`；
    - **Futility 跳过**（L256-260）：`!isChecked && !isPVNode && newDepth<6 && !isDanger(play) && movesSearched>=movesSearchedCount && FutilityScore[newDepth][movesSearched] + roughEvaluate(play) < thisAlpha` → 跳过该着法（continue，不是 return）；
    - **PVS/LMR**（L265-290）：
      ```java
      if (isMove) {
          int kk = 2;
          if (!isChecked && newDepth>=3 && movesSearched>=movesSearchedCount) {
              if (movesSearched >= (movesSearchedCount+(5+newDepth))*2) kk=4;
              else if (movesSearched >= (movesSearchedCount+5+newDepth)) kk=3;   // 仅当 !isDanger(1-play)
          }
          if (kk>=2 触发) thisValue = -negaScout(-thisAlpha-1,-thisAlpha,newDepth-kk,node,false);
          else            thisValue = thisAlpha+1;         // 强制走零窗口重搜
          if (thisValue > thisAlpha) {
              if (kk > 1) thisValue = -negaScout(-thisAlpha-1,-thisAlpha,newDepth-1,node,false); // 重归约
              if (thisValue > thisAlpha) thisValue = -negaScout(-beta,-thisAlpha,newDepth-1,node,true); // 全窗口
          }
      } else {
          thisValue = -negaScout(-beta,-thisAlpha,newDepth-1,node,true); isMove=true;   // 首着全窗口
      }
      ```
      实际条件里还嵌套了 `movesSearched>=movesSearchedCount && !isDanger(1-play)`（L267-272）：
      ```java
      if (!isChecked && newDepth>=3 && movesSearched>=movesSearchedCount) {
          if (movesSearched>=movesSearchedCount && !isDanger(1-play)) {
              if (movesSearched>=(movesSearchedCount+(5+newDepth))*2) kk=4;
              else if (movesSearched>=(movesSearchedCount+5+newDepth)) kk=3;
          }
          thisValue = -negaScout(-thisAlpha-1, -thisAlpha, newDepth-kk, nodeLinkTemp, false);
      } else {
          thisValue = thisAlpha+1;
      }
      ```
    - **结果处理**（L294-314）：更新 bestValue/bestNodeLink；`thisValue >= beta` 时：若非空着节点且当前着法不是 killer 本身，写入 killer 表（`killerMove[depth][1]=[0]; [0]=moveNode`），标记 `entryType=hashBeta`，break；`thisValue > thisAlpha` 时 `thisAlpha=thisValue`，`entryType=hashPV`。
12. **收尾**（L317-334）：有最佳着法时建立链 `lastLink.setNextLink(bestNodeLink)`；若 `entryType != hashAlpha` 则历史加分 `cHistorySort.setCHistoryGOOD(bestMoveNode, depth)`；写置换表 `setTranZobrist(entryType, bestValue, depth, play, bestMoveNode)`；返回 bestValue。无着法返回 `-(maxScore-lastLink.depth)`。

### 4.5 静态搜索 quiescSearch（SearchEngine L163-239）

```java
play = 1 - lastLink.play;
if (王被吃) return -(maxScore-lastLink.depth);
lastLink.chk = isChecked;                       // 由调用方传参 isChecked
if (isLongChk(lastLink)) return LONGCHECKSCORE; // 长将
if (isDraw(lastLink)) return drawScore;         // 双方无攻击子
if (lastLink.depth >= 64) return fineEvaluate(play);   // 深度保险丝
if (!isChecked) {                               // stand-pat（仅非被将时）
    thisValue = fineEvaluate(play);
    if (thisValue > bestValue) {
        if (thisValue >= beta) return thisValue;
        bestValue = thisValue;
        if (thisValue > alpha) alpha = thisValue;
    }
}
MoveNodesSort sort = new MoveNodesSort(play, chessQuiescMove, isChecked);  // QUIESDEFAULT 模式
while ((moveNode = sort.quiescNext()) != null && !sort.isOver()) {
    moveOperate;
    if (checked(play)) { unMoveOperate; continue; }        // 不自杀
    nodeLinkTemp = new NodeLink(play, moveNode, zob32, zob64, true);  // isQuiesc=true
    nodeLinkTemp.setLastLink(lastLink);
    thisValue = -quiescSearch(-beta, -alpha, nodeLinkTemp, chessQuiescMove.checked(1-play));
    unMoveOperate;
    if (thisValue > bestValue) { bestValue=thisValue; godNodeLink=nodeLinkTemp; if (>alpha) alpha=thisValue; if (>=beta) break; }
}
return isMove ? bestValue : -(maxScore-lastLink.depth);
```

- 只有被将军时才在吃子之后再枚举全部着法（`MoveNodesSort.quiescNext` L58-66），否则只搜"好"吃子（`ChessQuiescMove` 中 destScore>=150 的那些）+其余吃子（generalMoveList 也包含非吃子但正常情况下不会走到，因为非吃子进 generalMoveList——等等：Quiesc 的 savePlayChess 对**非吃子**也会进 generalMoveList，而 quiescNext 的 EATMOVE 只消费 goodMoveList，非被将时不会切到 OTHERALLMOVE，所以非吃子不会被搜索；被将时会切到 OTHERALLMOVE，此时 genNopMoveList 生成非吃子）。
- 长将返回 `LONGCHECKSCORE=8888`，将死返回 `±(maxScore-depth)`。
- 空着裁剪在此函数中被注释掉了（L198-204）。

### 4.6 特殊判断

- `isLongChk`（L240-260）：`lastLink.chk` 为真时，从上一节点沿 `lastLink` 链回溯，若遇到与当前节点 Zobrist32+64 相同的局面 → 长将；遇到任何吃子则终止（不再回溯）。
- `isDraw`（L267-273）：双方 `getAttackChessesNum`（车马炮兵）都为 0。
- `isDanger(play)`（L274-286）：play 方的车马炮在 `DangerMarginBit[play]`（黑/红危险区掩码表 L287-313）内的数量 >=3。
- `RAdapt(depth)`（L102-113）：`<=6→2, <=8→3, else 4`。
- `FutilityScore[d][k] = (int)(d*1.29*155) - k*d*10`，静态块 L19-30。
- 死代码：`FutilityMoveCounts`、`razor_margin`、`r1/r2/r3`、`RazorDepth`、`testLink`、`chkNum`、`countDepth`、`stopDepth` 均为定义后未使用。

### 4.7 PrincipalVariation 的作用

它是唯一实际使用的搜索实现，负责：
1. 根节点全着法枚举 + 过滤自将 + 初始排序；
2. 迭代加深（从 4 到难度 depth）调度；
3. 根 PVS（`rootNegaScout`）；
4. 完整内部 PVS（`negaScout`）+ 静态搜索 + 置换表 + 空着 + LMR + Futility + IID；
5. 维护 killer 表（按 depth 索引，深度上限 64）。

---

## 5. 评估函数

### 5.1 类职责与启用情况

| 类 | 状态 | 说明 |
|---|---|---|
| `EvaluateCompute` | 抽象基类 | 子力价值常量、`chessBaseScore[48]`、`chessMobility`、`chessAllMove`、分区表、炮检测工具、`AttackDirection/DefenseDirection` 位掩码 |
| `EvaluateComputeMiddleGame` | **启用（中局）** | `AICoreHandler.searchEngineFactory` L98-99 |
| `EvaluateComputeEndGame` | **启用（残局）** | L100-102；且残局时 `depth++`（L102） |
| `EvaluateComputeMiddle` | **废弃** | `evaluate()` L80 `if(true){ return score[play]-score[1-play]; }`，后面全部死代码 |
| `EvaluateComputeOther` | **废弃** | `evaluate()` L43 同样提前 return |

阶段判定 `AICoreHandler.getPhase()`（L112-130）：

```java
redChessNum   = 红车 + 红马 + 红炮 + (红兵>3 ? 1 : 0);
blackChessNum = 黑车 + 黑马 + 黑炮 + (黑卒>3 ? 1 : 0);
if (redChessNum + blackChessNum < 7) → END_GAME else MIDDLE_GAME
```

### 5.2 子力价值（EvaluateCompute L15-27）

```java
KINGSCORE=3000, CHARIOTSCORE=1300, KNIGHTSCORE=490, GUNSCORE=610,
ELEPHANTSCORE=200, GUARDSCORE=200, SOLDIERSCORE=100;
chessBaseScore[48]: 每个棋子索引对应一个值（16-31 黑、32-47 红；King=3000，车=1300...）
```

**动态调整**（`AICoreHandler.moveBegin` L132-142，每次搜索前执行）：

```java
兵/卒(27-31,43-47) = 100 + (11 - 对方攻击子数) * 8;
马(19,20,35,36)    = 490 + (32 - 全场剩余棋子数) * 6;
炮(21,22,37,38)    = 610 - (32 - 全场剩余棋子数) * 6;
```

注意时序陷阱：`setLocalVariable` 中先构造搜索器（此时 `SearchEngine` 构造函数已用**旧的**静态表算出 `baseScore`），之后 `run()` 里才调用 `moveBegin` 修改静态表。搜索中吃子/走子的增量更新（`moveOperate` 用 `evaluateCompute.chessBaseScore`）会用**新值**。Python 复刻必须保留这个顺序。

### 5.3 位置价值表（棋子位置分数表）

每个评估类都有一张 `chessSiteScoreByRole[15][90]`（按角色索引：1-7 红、8-14 黑），通过 `chessAttachScore(role, site)` 查询（各文件同名方法）。数据均为 90 个 int 的硬编码数组。

**启用版本的数据位置**：
- 中局：`EvaluateComputeMiddleGame` L220-337（blackKnightAttach、blackGunAttach、blackChariotAttach、blackSoldierAttach、ElephantAttch、GuardAttach、kingAttach），红方表由 `Tools.exchange(blackXxx)` 镜像生成 L320-323。
- 残局：`EvaluateComputeEndGame` L75-174，同样红方镜像 L175-178。
- 红黑镜像 `Tools.exchange`（L110-123）：我在 Python 里验证过，它在 90 坐标下等价于 `(row,col) → (9-row,col)`（45 对，行镜像）。

`baseScore` 的维护（`ChessMoveAbs.moveOperate` L82-99）：走子方 `-chessAttachScore(role,src) + chessAttachScore(role,dest)`；吃子时对方 `-= chessBaseScore[destChess] + chessAttachScore(destRole,dest)`。`unMoveOperate` L156-178 逆操作。

### 5.4 中局评估（EvaluateComputeMiddleGame.evaluate L35-218）

```java
score[RED] = baseScore[RED]; score[BLACK] = baseScore[BLACK];
dynamicCMPChessPartitionScore();                       // 动态调整分区评分表（士象数量影响）
for chess in 16..47 (alive):
    bAttack = chessAllMove(role, site, currplay);      // 该子控制范围（含空位/吃子）
    compPartitionScore(currplay, site, chess, partitionScore[currplay]);  // 分区累加
    bitBoardMove[currplay] |= bAttack;
    if (chessMinMobility[chess] > 0):
        mobility = chessMobility(role, site, bitBoard[currplay]);
        if (mobility < minMobility): score[currplay] -= (min-mobility)*mobilityRewards[chess];
        if 将是该子: kingUnMove[currplay]=true;
trimPartitionScore(partitionScore, attackPartition, defensePartition);
for i in {RED,BLACK}:
    opp = 1-i;
    score[i] += (bitBoardMove[i] ∩ 己方主攻子) * 10;   // proMainS=10
    score[i] += (bitBoardMove[i] ∩ 己方防御子) * 6;    // proDefenseS=6
    score[i] += (bitBoardMove[i] ∩ 对方主攻子) * 18;   // attMains=18
    score[i] += (bitBoardMove[i] ∩ 对方防御子) * 9;    // attDefenseS=9
    // 炮的特殊分：
    if (gunNum>0):
        if (对方攻击子+防御子-1 > 5 && exposedCannon(i,oppKingSite,...) != -1):
            score[i] += 曼哈顿距离 * 45; weakness=true;
        if (bottomCannon(i,oppKingSite,...) != -1 && 距离<=3): score[i] += 100; weakness=true;
    if (restChariot(i,oppKingSite,...) != 1): score[i] += 30;   // 注意 !=1 的语义（几乎总成立）
    if (weakness): 对方左/中/右防御分区各 -1
    if (kingUnMove[opp]): 对方三个防御分区各 -v（weakness 时 v=2）
    // 对方将偏位时对应防御分区 -1
    // 三路攻防比较：attackPartition[i][side] > defensePartition[opp][side] 时 +30*差
    // 缺士象：对方象<2 且士>=2 且己方有炮 → +60；对方士<2 且己方有马 → +60
    // 有车/马/炮各 +100（残存子力奖励）
return score[play] - score[1-play];
```

关键参数表：
- `chessMinMobility`/`chessMobilityRewards`（L13-25）：车 min=19 reward=50；马 min=8 reward=12；炮 min=19 reward=2；其余 0。
- 分区评分表 `attackChessPartitionScore/defenseChessPartitionScore` L181-191，按角色类型给 2/3/4 分（车=4、马炮=3、兵士象=2），并由 `dynamicCMPChessPartitionScore` L201-222 动态调整士象/马炮的值。
- `chessRolePartitionSite[role][site]` L414-417：每张位置表把 90 格映射到分区代号 {1,2,3,4,5,6,31,32,33,64,65,66}。
- `trimPartitionScore` L162-179：红方 attack=[1,2,3] defense=[4,5,6]；黑方相反。
- 炮检测工具：`exposedCannon`（空头炮/当头炮，L129-136）、`bottomCannon`（沉底炮，用隔两子攻击表 L141-148）、`restChariot`（L153-160）。

### 5.5 残局评估（EvaluateComputeEndGame.evaluate L26-55）

```java
score[R]=baseScore[R]; score[B]=baseScore[B];
for curplay in {RED,BLACK}:
    soldierNum = 兵数; gunNum=炮数; knightNum=马数;
    if (soldierNum>=2):
        soldierAttack = 所有兵的攻击位置并集;
        score[curplay] += soldiersProtected[ (soldierAttack ∩ 己方兵位).Count() ];  // {0,55,150,300,400,500}
    opponentGuardNum = 对方士数;
    if (gunNum>0)    score[curplay] += gunOpptNotGuard[opponentGuardNum]    * (gunNum==2?1.7:1);  // {0,40,110}
    if (knightNum>0) score[curplay] += knightOpptNotGuard[opponentGuardNum] * (knightNum==2?1.7:1); // {110,40,0}
return score[play]-score[1-play];
```

注意 `* 1.7` 后会被截断为 int（Java 赋值给 int 没有，但这里 `+=` 到 int，浮点乘结果截断为整型——`score[curplay] += int * double` 会做复合赋值，Java 会隐式窄化。实际编译为 `score += (int)(...)`。Python 复刻需 `int()` 截断）。

`getSoldiersAttackBitBoard`（L63-73）用 `chessAllMove` 计算士兵攻击位。

### 5.6 评估的调用链

- `SearchEngine.fineEvaluate(play)`（L115-118）：`count++` 后 `evaluate.evaluate(play)`。
- `roughEvaluate(play)`（L123-125）：`baseScore[play]-baseScore[1-play]`（不遍历棋子，用于 Futility）。
- 叶子/静态搜索 stand-pat 用。

---

## 6. Zobrist 哈希与置换表

### 6.1 Zobrist 表

`ChessConstant` L101-102：

```java
public static final long ChessZobristList64[90][15];
public static final int  ChessZobristList32[90][15];
```

- 第一维是 site（0-89），第二维是**角色**（1-14），索引 0 不用。
- **没有走棋方键、没有特殊规则键**。红黑双方的同一角色值不同（1-7 vs 8-14），因此天然区分颜色。
- 计算（`TranspositionTable.genStaticZobrist32And64OfBoard` L93-102）：对棋盘每个非空格 `board[i] > NOTHING`，`key ^= ChessZobristList[site][chessRoles[chess]]`。
- 增量维护（`moveOperate` L135-151）：`XOR 源格源子、XOR 目标格被吃子（若有）、XOR 目标格源子`；`unMoveOperate` L156-171 逆序恢复。
- 实例字段 `boardZobrist32/64` + 静态 `boardZobristStatic32/64`；UI 在人类走子后调用 `synchroZobristBoardToStatic` 把当前局面的静态值同步，AI 新引擎从静态值拷贝。

### 6.2 InitZobristList32And64

- 2709 行，**纯数据**：两个方法 `initChessZobristList32()` / `initChessZobristList64()`，各 1350 条（90×15）常量赋值。
- 32 位值全部在 [0, 2^31)（均为正 int）；64 位值均在 [0, 2^63)。
- **可以用代码生成**：Zobrist 键只需要程序内部自洽（生成与增量更新用同一张表）。用 Python `random.getrandbits` 生成即可。唯一区别是哈希碰撞模式可能与原 Java 版本不同，从而在极少数情况下影响置换表命中/覆盖行为。若要求"逐步完全复刻"（包括置换表命中），则必须移植这 2700 个常量（可直接解析该 Java 文件）。
- 原始生成代码被注释在 `ChessInitialize.genBoardZobrist`（L421-429），公式为 `Math.abs((nextLong()<<15)^(nextLong()<<30)^(nextLong()<<45)^(nextLong()<<60))`，但**保存的表与这段代码不存在可验证关系**（无法用同一公式+未知种子确定复现），所以只能"抄表"或"重生成"。

### 6.3 置换表结构（TranspositionTable）

- 全局静态：`HashItem[][][] tranZobrist = new HashItem[2][TRANZOBRISTSIZE][2]`（L62）。
  - 第 1 维：**走棋方 play**（0/1 各一张表）。
  - 第 2 维：槽位，槽号 `x = boardZobrist32 & TRANZOBRISTSIZE`（按位与，不是取模）。
  - 第 3 维：0=`OVERRIDESTRAIGHT`（"始终覆盖"槽），1=`OVERRIDESTEP`（"按步/深度替换"槽）。
- 大小：`setDefaultHashSize` 默认 `0x7FFFF`（524287）；UI 菜单可设 `0xFFFFF` 或 `0x1FFFFF`（ChessBoardMain L583-594）。
- 条目 `HashItem`：`checkSum(long=boardZobrist64)`、`entry_type(1=hashBeta 下界/2=hashAlpha 上界/3=hashPV 精确值)`、`value`、`depth`、`moveNode`、`isExists`。

**写入（setTranZobrist L319-330）**：

```java
if ((value>=8000 && value<=9000) || (value>=-9000 && value<=-8000)) return;  // 不存长将等分数
x = boardZobrist32 & TRANZOBRISTSIZE;
HashItem hi0 = setTranZobristOverrideByStep(entry_type,value,depth,play,moveNode,x); // 深度替换槽
setTranZobristOverride(entry_type,value,depth,play,moveNode,x,hi0);                  // 覆盖槽
```

- `setTranZobristOverrideByStep`（L287-315）：若 STEP 槽已有条目且 `isExists` 且旧 depth > 新 depth → **直接放弃新条目**（返回 null）；否则把旧条目踢出（返回作为 `hi1`），新条目写入 STEP 槽。
- `setTranZobristOverride`（L264-283）：若上一步踢出了旧条目，则把旧条目写入 STRAIGHT 槽；否则新条目直接覆盖 STRAIGHT 槽。

即每个槽保存 2 条记录：STEP 槽保留较深搜索结果，STRAIGHT 槽实际是"最近一次写入"。`cleanTranZobrist`（L67-78）只把两个 play 表的 STEP 槽 `isExists=false`（AI 每步结束时调用 `AICoreHandler.moveEnd` L150）。

**读取（getTranZobrist L335-360）**：

```java
x = boardZobrist32 & TRANZOBRISTSIZE;
hi = getTranZobristOverrideByStep(play,x);        // 要求 checkSum==boardZobrist64
if (hi != null) {
    result = getTranZobristByHashItem(hi, depth, alpha, beta);
    if (result != FAIL) return result;
    tranGodMoveNode.set(0, hi.moveNode);  value[0]=hi.value;
}
hi2 = getTranZobristOverride(play,x);
if (hi2 != null) {
    result = getTranZobristByHashItem(hi2, depth, alpha, beta);
    if (result != FAIL) return result;
    tranGodMoveNode.set(0, hi2.moveNode); if (hi==null || hi.depth<hi2.depth) value[0]=hi2.value;
}
return FAIL;   // FAIL = Integer.MIN_VALUE + 1
```

`getTranZobristByHashItem`（L361-391）：
- mate 调整：`value > mateNode(9899)` → `value -= (depth - hi.depth)`；`value < -9899` → `value += (depth - hi.depth)`；
- `hi.depth < depth` → FAIL（浅结果不能用于更深搜索）；
- entry_type：PV 直接返回；Beta（下界）要求 `value >= beta`；Alpha（上界）要求 `value <= alpha`。

**着法存储**：只有 `hashPV`/`hashBeta` 更新时通过 `bestMoveNode` 存 TT 着法（nested：`setTranZobrist` 第 6 参）。`hashAlpha` 时不传着法（`if(entryType!=hashAlpha) bestMoveNode=...` L321-325）。

**根槽写入**：IID 时 `setRootTranZobrist(play, move)` 只写 STRAIGHT 槽（L177-185）的 checkSum+moveNode（不改 depth/type/value）。

**其他**：`fenLib` 是开局面库（HashMap<boardZobrist64, List<MoveNode>>），`getTranZobristFen` 随机选一个；`loadBook` 在 ChessInitialize 中被注释（L196-197），当前版本未加载。`setTranZobrist(MoveNode)` 与 `FEN` 常量属于库函数。

---

## 7. 历史启发与着法排序

### 7.1 CHistoryHeuritic（L11-35）

```java
public static int[][] cHistory = new int[8][256];   // [基础类型 0-7][目标格 0-255]
public void setCHistoryGOOD(MoveNode m, int depth) {
    if (m != null) cHistory[chessRoles_eight[m.srcChess]][m.destSite] += 2 << depth;  // = 2^(depth+1)
}
public void setCHistoryBad(MoveNode m, int depth) {
    if (m != null) cHistory[...][...] -= 2 >> depth;   // 疑似 << 笔误；但调用处被注释，实际不生效
}
public int getCHistory(MoveNode m) { return cHistory[...][m.destSite]; }
```

- 更新时机：仅在 `negaScout` 找到一个 `entryType != hashAlpha` 的 bestMoveNode 时（L321-325）。
- 衰减：`AICoreHandler.moveEnd`（L143-151）把整张表 `/= 512`，在每步 AI 结束后执行。
- 注意第二维 256 > 90（浪费），且不同棋子索引共享同一"基础类型"行（如红黑马共用）。
- `ChessMovePlay.savePlayChess` L80 用 `cHistory[type][destSite] + (isOppProtect?0:256)` 作为通用着法排序分。

### 7.2 MoveNodeList（movelist/MoveNodeList.java）

定长 `MoveNode[] tables` + `size`，`add` 不做边界检查（容量在构造时给定：goodMoveList=30，generalMoveList=100，根=100，killer/TT=2/4）。`get(i)` 对 `i>=size` 返回 null（L33-38）。

### 7.3 MoveNodesSort（状态机）

两种模式：

**主搜索模式**（构造函数 L24-31，`moveType=TRANGODMOVE1`），`next()` L81-150 的阶段顺序：

1. `TRANGODMOVE1`：`tranGodMove.get(0)`（TT 首选着法），`legalMove` 校验，加入 `repeatMoveList`；
2. `TRANGODMOVE2`：`tranGodMove.get(1)`（TT 第二着法，来自第二个 HashItem），排除与第一着法相同；
3. `KILLERMOVE1/2`：`KillerMove[0]/[1]`，排除与前两个 TT 着法重复；
4. `EATMOVE`：首次进入时 `oppAttackSite = chessMove.getOppAttackSite(play)`（计算对方全体攻击位，用于保护判断），`genEatMoveList`；从 `goodMoveList` 用选择排序取最大 `score`（`getSortAfterBestMove` L215-228）；
5. `OTHERALLMOVE`：`genNopMoveList`，从 `generalMoveList` 选择排序；
6. 穷尽后 `moveType=OVER`，`next()` 返回 null。

统计字段 `currType`（0-5：tran1,tran2,kill1,kill2,eatmove,other）会被搜索层用于判断"这个着法是不是 killer"以及更新统计数组 `values/oppProtected/oppNotProtected`（后者实际未在输出中使用）。

**静态搜索模式**（构造函数 L35-40，`moveType=QUIESDEFAULT`），`quiescNext()` L44-80：
- 先 `EATMOVE`（只有 `goodMoveList`——由 Quiesc 分类逻辑决定）；
- 若 `isChecked` 则继续 `OTHERALLMOVE`（全部着法），否则 OVER。
- quiesc 模式不设置 `oppAttackSite`（Quiesc 不使用）。

`repeatMoveList`（容量 4，L18）：保存已返回的 TT/killer 着法；`ChessMovePlay.savePlayChess` 遇到重复时将其置 null 并跳过，避免同一着法在列表中出现两次。

**NodeLink**（L15-104）：双向链表节点，用于：
- PV 链：`lastLink/nextLink`，`depth`（根为 0，`setLastLink` 时 +1）；
- `play`：上一步走子方（当前节点表示的局面轮到 `1-play`）；
- `boardZobrist32/64`：走完后的局面哈希（用于长将检测与 TT）；
- `chk`：该局面是否被将（搜索层设置）；
- `isNullMove`：空着节点标志（其 `moveNode==null`）；
- `isQuiesc`：静态搜索节点标志；
- `getMoveNode()==null` 用于判断到达链首。

---

## 8. 其他关键细节

### 8.1 UI 如何触发 AI

1. 人在 `mousePressed` 中选子（校验 `board[i] & chessPlay[play]`）与落子（`cmp.legalMove`）。
2. 合法则构造 `MoveNode` → `showMoveNode`（L696-702）：`move(moveNode)` 更新图标 + `cmp.moveOperate(moveNode)` 更新棋盘 + `transTable.synchroZobristBoardToStatic()`。
3. `new NodeLink(play, zob32, zob64)` 作为下一步链节点接到 `moveHistory` 后面，`moveHistory` 前进（L466-469）。
4. `opponentMove()`（L604-615）：`checkGameOver()` → `turn_num++` → `play=1-play` → 若 `android[play]` 则 `computeThinkStart()`。
5. `computeThinkStart`（L616-654）：若开启"后台思考"且 `guessLink` 与当前 `moveHistory` 相同（人类走了电脑猜的那步）则直接复用后台搜索结果；否则 `backstageAIThink.setStop()` 并新建线程 `computeThink()`。
6. `computeThink`（L655-664）新线程：
   ```java
   _AIThink.setLocalVariable(computerLevel, chessParamCont, moveHistory); // 深拷贝 ChessParam
   _AIThink.launchTimer();   // 启动超时定时器
   _AIThink.run();           // 同步搜索
   computeAIMoving(moveHistory.getNextLink());
   ```
7. `computeAIMoving`（L666-676）：`moveHistory = nodeLink`（AI 搜索返回的 PV 链节点）→ `showMoveNode` → `opponentMove` → `backstageThink`。

**线程与时间控制**：
- 搜索在独立 `Thread` 中（`new Thread(){...}.start()`）。
- `AICoreHandler.launchTimer`（L161-169）：`new Timer().schedule(task, time)`，到点调用 `setStop()` → `seEngine.isStop=true`。
- 搜索循环在迭代之间（`for d<=depth && !isStop`）和节点循环内（`if(isStop) break`）检查退出；已完成的迭代结果保留。
- 每次 AI 调用 `setLocalVariable` 都新建 `PrincipalVariation`（全新 `isStop=false`），并做 `new ChessParam(chessParam)` 深拷贝（`ChessParam.copyToSelf` L62-118 拷贝 board/allChess/位置位/计数/掩码/baseScore）。

**难度等级 → 深度/时限**（`ComputerLevel` L2-22）：

| 枚举 | 中文 | depth | time（构造器 ×1000ms） |
|---|---|---|---|
| greenHand | 入门 | 6 | 4 s |
| introduction | 初级 | 7 | 8 s |
| amateur | 业余 | 8 | 16 s |
| career | 专业 | 9 | 32 s |
| master | 大师 | 15 | 64 s |
| invincible | 无敌 | 32 | 3600 s |

另外残局 `searchEngineFactory` 会给 `depth++`（L102）。

### 8.2 AICoreHandler 职责

| 方法 | 行号 | 职责 |
|---|---|---|
| `run(isGuess)` | L42-65 | `setDefaultHashSize` → `moveBegin()`（动态子力表）→ `searchMove` → 非猜测时 `moveEnd()`（历史衰减+清 TT 的 STEP 槽）→ 打印耗时/分数/叶子数 |
| `setLocalVariable` | L66-72 | 记录 depth/time/moveHistory，深拷贝 ChessParam，构造搜索器 |
| `guessRun` | L73-77 | 后台猜测：在副本棋盘上 apply 猜测着法后搜索，再 unapply |
| `searchEngineFactory` | L78-106 | 按 `getPhase()` 选择 EvaluateComputeMiddleGame/EndGame（残局 depth++），返回 PrincipalVariation |
| `getPhase` | L112-130 | 中残局判定（见 5.1） |
| `moveBegin` | L132-142 | 动态子力价值调整 |
| `moveEnd` | L143-151 | `cHistory /= 512`；`cleanTranZobrist()` |
| `setStop` | L152-160 | 置 `isStop` + 取消计时器 |
| `launchTimer` | L161-169 | 到点停搜 |

`blockQueue`、`MDFSEARCHENGINETYPE`、`mdfdV` 是历史遗留（未使用）。

### 8.3 Tools 关键工具

| 方法 | 行号 | 说明 |
|---|---|---|
| `parseFEN(String)` | L59-105 | 解析 FEN 棋盘部分为 90 长度 int[]（棋子索引 16-47，空 0）；字母表 L62-78 |
| `fenToFENArray` | L48-58 | 按空白切分 FEN 为 8 段（实际第 0 段是着法，用于开局面库） |
| `exchange(int[90])` | L110-123 | 90 坐标行镜像（row↔9-row），用于红黑位置表互转 |
| `getBoradSite(row,col)` | L326-332 | `row*9+col` |
| `isBoardTo255(site)` | L126-133 | 16×16 坐标合法性（初始化用） |
| `saveFEN`/`loadBook`/`writeToFile` | L151-325 | 存档/开局库（引擎外，可剥离；`loadBook` 依赖 `D://book.txt`） |
| `printBoard/printBitBoard` | L134-147/L334-347 | 调试 |

"棋子分数、位置表"实际在 `EvaluateCompute` 系列类中，不在 Tools。

---

## 9. 核心算法伪代码（带 Java 行号）

### 9.1 迭代加深 + 根 PVS（PrincipalVariation.searchMove L40-94 / rootNegaScout L95-148）

```
def search_move(alpha, beta, depth):                      # L40
    reset MoveNodesSort counters
    moveHistory.depth = 0
    setStretchNeedNumByDepth(depth)
    sort = MoveNodesSort(play=1-moveHistory.play, tt=[], killerMove[depth], chessMove, isChecked=False)  # L54
    rootMoves = []
    initScore = 100
    while (m = sort.next()) != None and not sort.isOver():          # L59 枚举根着法
        chessMove.moveOperate(m)
        if not chessMove.checked(currPlay):                          # L61 过滤走完自将
            m.score = initScore; initScore -= 1; rootMoves.add(m)
        chessMove.unMoveOperate(m)
    s = 0
    for d in range(4, depth+1):                                      # L68 固定从 4 层迭代
        if isStop: break
        s = root_nega_scout(alpha, beta, d, rootMoves, moveHistory)  # L70
        # L71-78 把本层 PV 链写入 killerMove[d+1..0]
        next = moveHistory.getNextLink(); k = d+1
        while next != None and k >= 0:
            killerMove[k][1] = killerMove[k][0]
            killerMove[k][0] = next.getMoveNode()
            k -= 1; next = next.getNextLink()
    return s                                                          # L93

def root_nega_scout(alpha, beta, depth, rootMoves, lastLink):         # L95
    play = 1 - lastLink.play
    isChecked = chessMove.checked(play); lastLink.chk = isChecked
    thisAlpha = alpha; bestValue = -maxScore-2; isMove = False
    i = 0
    while i < rootMoves.size:                                        # L109
        m = getSortAfterBestMove(rootMoves, i); i += 1                # L110 选择排序取当前最优
        chessMove.moveOperate(m)
        child = NodeLink(play, m, zob32, zob64); child.setLastLink(lastLink)
        if isMove:
            v = -nega_scout(-thisAlpha-1, -thisAlpha, depth-1, child, False)   # L116 零窗口
            if v > thisAlpha:
                v = -nega_scout(-beta, -thisAlpha, depth-1, child, True)       # L119 全窗口重搜
        else:
            v = -nega_scout(-beta, -thisAlpha, depth-1, child, True)           # L122 首着全窗口
            isMove = True
        chessMove.unMoveOperate(m)
        m.score = v                                                   # L126 供下轮排序
        if v > bestValue:
            bestValue = v; bestNodeLink = child
            if v > thisAlpha: thisAlpha = v
        if isStop: break
    if isMove: lastLink.setNextLink(bestNodeLink); return bestValue
    else:      return -(maxScore - lastLink.depth)                    # L144 无着法=将死
```

### 9.2 内部 PVS negaScout（PrincipalVariation L154-337）

```
def nega_scout(alpha, beta, depth, lastLink, isPVNode):
    play = 1 - lastLink.play
    if allChess[chessPlay[play]] == NOTHING: return -(maxScore - lastLink.depth)   # L158 王被吃
    bestValue = lastLink.depth - maxScore
    if bestValue > beta: return bestValue                                          # L162 下界保护

    tranGodMoveNode = MoveNodeList(2); value=[0]
    score = transTable.getTranZobrist(alpha, beta, depth, play, tranGodMoveNode, value)
    if score != FAIL: return score                                                 # L167 TT 命中

    isChecked = chessMove.checked(play); lastLink.chk = isChecked                  # L171
    if isLongChk(lastLink): return LONGCHECKSCORE                                  # L175 长将 8888
    if (not lastLink.isNullMove) and lastLink.getMoveNode().isEatChess():
        if isDraw(lastLink): return drawScore                                      # L181 双方无攻击子
    if isChecked: depth += 1; checkNum += 1                                        # L185 将军延伸

    entryType = hashAlpha
    if depth <= stopDepth:                                                         # L192 stopDepth 恒 0
        return quiesc_search(alpha, beta, lastLink, isChecked)

    if (not lastLink.isNullMove) and (not isChecked) and (not isPVNode):           # L201 空着裁剪
        if depth >= 2:
            R = RAdapt(depth)                                    # <=6:2, <=8:3, else 4
            attackNum = chessParam.getAttackChessesNum(play)
            if attackNum > 0:
                nullLink = NodeLink(play, isNullMove=True, zob32, zob64); nullLink.setLastLink(lastLink)
                v = -nega_scout(-beta, -beta+1, depth-R-1, nullLink, False)
                if v >= beta:
                    if attackNum > 2 and depth < 6: return v                   # L211 弱验证
                    v = -nega_scout(-beta, -beta+1, depth-R+1, nullLink, False) # L215 验证
                    if v >= beta: return v

    if depth >= 6 and isPVNode and tranGodMoveNode.get(0) is None:                 # L224 IID
        nega_scout(alpha, beta, depth-2, lastLink, isPVNode)
        if lastLink.getNextLink() != None:
            tranGodMoveNode.set(0, lastLink.getNextLink().getMoveNode())
            transTable.setRootTranZobrist(play, lastLink.getNextLink().getMoveNode())

    isMove = False; thisAlpha = alpha; bestNodeLink = None
    movesSearched = 0; curType = -1
    sort = MoveNodesSort(play, tranGodMoveNode, killerMove[depth], chessMove, isChecked)  # L236
    movesSearchedCount = 10 if isPVNode else 5                                     # L238

    while (m = sort.next()) != None and not sort.isOver():                          # L239
        chessMove.moveOperate(m)
        if chessMove.checked(play): chessMove.unMoveOperate(m); continue            # L243 不自杀
        if (not isChecked) and (not isPVNode) and depth < 6 and (not isDanger(play)) \
           and movesSearched >= movesSearchedCount \
           and FutilityScore[depth][movesSearched] + roughEvaluate(play) < thisAlpha:
            chessMove.unMoveOperate(m); movesSearched += 1; continue                # L256 Futility 跳过
        child = NodeLink(play, m, zob32, zob64); child.setLastLink(lastLink)

        if isMove:                                                                  # L265 PVS + LMR
            kk = 2
            if (not isChecked) and depth >= 3 and movesSearched >= movesSearchedCount:
                if movesSearched >= movesSearchedCount and (not isDanger(1-play)):
                    if movesSearched >= (movesSearchedCount+(5+depth))*2: kk = 4
                    elif movesSearched >= (movesSearchedCount+5+depth):   kk = 3
                v = -nega_scout(-thisAlpha-1, -thisAlpha, depth-kk, child, False)
            else:
                v = thisAlpha + 1                        # 强制进入重搜分支
            if v > thisAlpha:
                if kk > 1:
                    v = -nega_scout(-thisAlpha-1, -thisAlpha, depth-1, child, False)  # 解除归约
                if v > thisAlpha:
                    v = -nega_scout(-beta, -thisAlpha, depth-1, child, True)          # 全窗口
        else:
            v = -nega_scout(-beta, -thisAlpha, depth-1, child, True)                  # 首着
            isMove = True

        chessMove.unMoveOperate(m); movesSearched += 1
        if v > bestValue:
            bestValue = v; bestNodeLink = child
            if v >= beta:                                        # L298 beta 截断
                if (not lastLink.isNullMove) and sort.currType not in (kill1, kill2):
                    killerMove[depth][1] = killerMove[depth][0]
                    killerMove[depth][0] = m
                curType = sort.currType; entryType = hashBeta; break
            if v > thisAlpha:
                curType = sort.currType; thisAlpha = v; entryType = hashPV

    if isMove:
        lastLink.setNextLink(bestNodeLink)
        bestMoveNode = None
        if bestNodeLink != None and entryType != hashAlpha:
            bestMoveNode = bestNodeLink.getMoveNode()
            cHistorySort.setCHistoryGOOD(bestMoveNode, depth)        # L323 历史加分
        transTable.setTranZobrist(entryType, bestValue, depth, play, bestMoveNode)
        return bestValue
    else:
        return -(maxScore - lastLink.depth)                          # L333 无着法=将死
```

### 9.3 静态搜索（SearchEngine L163-239）

```
def quiesc_search(alpha, beta, lastLink, isChecked):
    play = 1 - lastLink.play
    if allChess[chessPlay[play]] == NOTHING: return -(maxScore-lastLink.depth)  # L166 王被吃
    lastLink.chk = isChecked
    if isLongChk(lastLink): return LONGCHECKSCORE                               # L174 长将
    if isDraw(lastLink):    return drawScore                                    # L178 和棋
    bestValue = -maxScore-2
    if lastLink.depth >= 64: return fineEvaluate(play)                          # L183 保险丝
    if not isChecked:                                                           # L186 stand-pat
        thisValue = fineEvaluate(play)
        if thisValue > bestValue:
            if thisValue >= beta: return thisValue
            bestValue = thisValue
            if thisValue > alpha: alpha = thisValue
    sort = MoveNodesSort(play, chessQuiescMove, isChecked)                      # QUIESDEFAULT
    while (m = sort.quiescNext()) != None and not sort.isOver():                # L210
        chessQuiescMove.moveOperate(m)
        if chessQuiescMove.checked(play): chessQuiescMove.unMoveOperate(m); continue   # L213
        child = NodeLink(play, m, zob32, zob64, isQuiesc=True); child.setLastLink(lastLink)
        v = -quiesc_search(-beta, -alpha, child, chessQuiescMove.checked(1-play))      # L219
        chessQuiescMove.unMoveOperate(m); isMove = True
        if v > bestValue:
            bestValue = v; godNodeLink = child
            if v > alpha: alpha = v
            if v >= beta: break
    return bestValue if isMove else -(maxScore-lastLink.depth)                  # L233-238
```

### 9.4 中局评估（EvaluateComputeMiddleGame.evaluate L35-218）

```
def evaluate(play):
    score = [baseScore[R], baseScore[B]]                       # L36-37 已含子力+位置增量
    dynamicCMPChessPartitionScore()                            # L45 按士象数更新分区表
    moveMask = [{},{}]; partition = [[0]*7,[0]*7]; kingUnMove=[False,False]
    for chess in 16..47:                                       # L47
        if allChess[chess] == NOTHING: continue
        side = BLACK if chess < 32 else RED
        bAttack = chessAllMove(role(chess), allChess[chess], side)      # 控制范围
        compPartitionScore(side, site, chess, partition[side])          # L59 分区评分
        moveMask[side] |= bAttack
        if chessMinMobility[chess] > 0:                                 # L63 机动性惩罚
            mob = chessMobility(role, site, ownMask[side])
            if mob < chessMinMobility[chess]:
                score[side] -= (chessMinMobility[chess]-mob)*chessMobilityRewards[chess]
                if role == KING: kingUnMove[side] = True
    trimPartitionScore(partition, attackPartition, defensePartition)    # L77
    for i in {R,B}:                                                     # L83
        opp = 1-i
        score[i] += count(moveMask[i] & mainAttack(i)) * 10             # L91-95
        score[i] += count(moveMask[i] & defense(i))    * 6
        score[i] += count(moveMask[i] & mainAttack(opp)) * 18
        score[i] += count(moveMask[i] & defense(opp))    * 9
        if gunNum[i] > 0:                                               # L106 炮特殊分
            if oppAllChessNum > 5 and exposedCannon(i, oppKingSite,...) != -1:
                score[i] += manhattan(oppKing, gun) * 45; weakness = True
            if bottomCannon(i, oppKingSite,...) != -1 and dist <= 3:
                score[i] += 100; weakness = True
        if restChariot(i, oppKingSite,...) != 1: score[i] += 30         # L130
        if weakness: defensePartition[opp][*] -= 1                      # L134-138
        if kingUnMove[opp]: defensePartition[opp][*] -= (2 if weakness else 1)
        将偏位 → defensePartition[opp][侧] -= 1                          # L150-173
        for side in {L,R,Mid}:                                          # L178-186
            if attackPartition[i][side] > defensePartition[opp][side]:
                score[i] += (attackPartition[i][side]-defensePartition[opp][side]) * 30
        if elephNum[opp] < 2 and guardNum[opp] >= 2 and gunNum[i] > 0: score[i] += 60
        if guardNum[opp] < 2 and knightNum[i] > 0:                     score[i] += 60
        if chariotNum[i] > 0: score[i] += 100                           # L204-212
        if knightNum[i]  > 0: score[i] += 100
        if gunNum[i]     > 0: score[i] += 100
    return score[play] - score[1-play]                                  # L217
```

### 9.5 残局评估（EvaluateComputeEndGame.evaluate L26-55）

```
def evaluate(play):
    score = [baseScore[R], baseScore[B]]
    for side in {R,B}:
        if soldiers[side] >= 2:
            atk = soldiersAttackMask(side) & soldiersMask(side)
            score[side] += soldiersProtected[count(atk)]          # {0,55,150,300,400,500}
        oppGuard = guards[1-side]
        if guns[side] > 0:    score[side] += int(gunOpptNotGuard[oppGuard]    * (1.7 if guns[side]==2 else 1))
        if knights[side] > 0: score[side] += int(knightOpptNotGuard[oppGuard] * (1.7 if knights[side]==2 else 1))
    return score[play] - score[1-play]
```

---

## 10. Python 精确复刻注意事项（陷阱清单）

1. **完全没有着法 int 编码**，不要发明；MoveNode 就是 5 int 对象。
2. **BitBoard 的 4 字切分**影响两处：`MSB` 的扫描顺序（红升序、黑按字降序）、`checkSum` 折叠键。若用 Python 单一大整数，务必单独实现这两个语义。
3. `checkSumOfKnight/Elephant` 的移位与掩码必须逐字保留（0/6/13/19 与 0/7/14/21），表 200 维足够（实测最大 149），但保留 200 或扩大均可。
4. **行/列表的第一维是"列 col/行 row"而不是坐标**（`ChariotBitBoardOfAttackRow[col][rowMask]`），且 `rowMask` 是 `boardBitRow` 原始 int（bit(8-col) 编码）；列同理（bit(9-row)）。
5. **`if (isEat && j==site) continue`** 只跳过"该行/列仅车自身"的状态；因该状态下无阻挡可吃，不产生行为差异（炮同理正确）。
6. 炮的攻击表只把"越过第一个阻挡后的第二个阻挡格"作为吃子落点；空格移动用 MoveChariotOrGun 表；压制位（FakeAttack）是炮架后的空位；隔两子表用于沉底炮检测。
7. 将军延伸 `depth++`、空着 R 值（2/3/4）、LMR 的 kk（2/3/4）与 `movesSearchedCount`（PV=10、非PV=5）都是精确常量。
8. Futility 是"跳过着法"而不是立刻返回；触发条件里的 `FutilityScore[newDepth][movesSearched]`（d*1.29*155 - k*d*10，整型截断）。
9. `isDanger(play)` 检查的是 `DangerMarginBit[play]`（黑/红各自半场靠九宫区域）中 play 方车马炮数量 >=3；注意 LMR 里用的是 `isDanger(1-play)`。
10. 将死分 `±(maxScore - depth)`，`maxScore=9999`；长将分 8888；和棋 0；`LONGCHECKSCORE`/8000-9000 区间分数不入置换表。
11. 置换表槽号是 `zob32 & size`（按位与）；每条两个子槽（STEP 深度替换 + STRAIGHT 覆盖）；读时先 STEP 后 STRAIGHT；mate 分数按 depth 差调整；`hi.depth < depth` 直接 FAIL。
12. **评估时序陷阱**：每次 AI 调用的顺序是 `new ChessParam 深拷贝` → `new PrincipalVariation`（此刻用静态子力表算 `baseScore`）→ `moveBegin()`（改静态子力表）→ `searchMove`。`baseScore` 的初始值与搜索中增量用的子力表可能来自不同版本，必须按此顺序复刻。
13. `EvaluateComputeMiddle`/`Other` 是死代码（`if(true) return`），只需实现 `MiddleGame` + `EndGame`；但 `Tools.exchange` 的镜像语义（r↔9-r）必须正确。
14. 历史表 `cHistory[8][256]`：更新是 `+= 2<<depth`（即 2^(depth+1)）；坏着法更新 `-= 2>>depth` 是疑似笔误且调用被注释；每步结束整表 `/=512`（整除）。
15. 根搜索迭代固定从 depth=4 开始；根着法列表每轮用上轮分数重排（选择排序，稳定语义要一致）；根节点不做 beta 截断直接返回。
16. killer 表按 `depth` 索引（`killerMove[64][2]`），且迭代加深每轮用 PV 路径覆写；搜索内 beta 截断时也会写 killer。
17. `MoveNodesSort` 的阶段顺序和 `getSortAfterBestMove` 的"选择排序 + 原地交换"要精确复刻（相同 score 的相对顺序影响剪枝路径）。
18. 置换表、历史表、静态 Zobrist 都是**全局共享**的（Java 版多线程后台思考会互相干扰），Python 可用全局单例，但若要做严格复刻建议同样全局。
19. UI 的 `cmp`（ChessMovePlay）与搜索引擎是两套对象，但共享 `ChessParam` 的引用？不——AI 搜索用深拷贝。UI 的 `cmp` 只服务于人类走子。
20. Zobrist 常量表可以自行生成（不影响正确性），若要复现哈希值则需移植原表；`InitZobristList32And64` 没有生成逻辑，是纯数据。
</task_result>
</task>