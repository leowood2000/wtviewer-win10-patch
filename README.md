# WTViewer 8.24 Win10 补丁

在 Windows 10 22H2 x64 上修复横河 WTViewer 8.24 通过 Agilent 82357B 采集 WT210 普通测量数据时遇到的 Start 无读数和 Stop 卡死问题。需要已有的 WTViewer 安装和可用的 GPIB 环境。

仓库直接提供已修补的 `tmctl.dll`，复制到你的 WTViewer 副本目录替换同名文件即可，也可用脚本从原版自行生成。二进制版权归横河电机所有，仅托管用于互操作目的的修补版；原版可从横河官网下载。替换前先关闭 WTViewer。

- `tmctl.dll` — GPIB 取样修复（SHA-256 `40bb4a7dfc1314bdf38b20faeb50806625498974e09cbd696f10811f5791b532`）。

## 生成和使用

1. 将现有 WTViewer 安装目录完整复制到可写目录，例如 `C:\WTViewerWin10`。
2. 在本仓库目录运行以下命令。将路径换成你的实际目录。

   ```powershell
   py -m pip install -r requirements.txt
   py .\wt-patch-tmctl.py "C:\Program Files (x86)\Yokogawa\WTViewer\tmctl.dll" "C:\WTViewerWin10\tmctl.dll"
   ```

3. 从副本启动 `WtViewer.exe`，选择 On-Line、GPIB 和 Normal Measurement。仪器需设为 488.2 模式，地址与软件中的设置一致。本机验证使用地址 1。需要保存时，在数值窗口启用 Auto Saving 并选可写的 CSV 路径。
4. 双击原安装目录中的程序可回到原版。也可把原版 DLL 重新复制到应用副本。

补丁生成器适配 SHA-256 为 `5bc57668140e6d075acdbab12f2a979594b5b5aa5d173b948745d2bcb2bbfd01` 的 `tmctl.dll` 2.1.6.0。仓库提供生成脚本，原版与修补后的 DLL 都在本机保管。

## Auto Ranging 电流轴显示缺陷（WT210，尚未修复）

**症状**：Wave 窗口勾选 Auto Ranging 后，I1 电流轴刻度只有 ±15.00m（0.015 A），波形压平成线；V1 电压轴正常。仪器 AUTO 量程解析在 0.5 A 档时，每次启动 WTViewer 后都会复现。

**重要更正（2026-11-14）**：本仓库此前提供的 `WtViewer.exe` NOP 补丁（把 VA 0x158c975 处的 `fmul qword ptr [0x1624a48]` 改为 NOP，即移除 ×0.01）**是错误修复，已从仓库移除**。×0.01 不是缺陷：型号枚举 5/6 的语义里，量程索引 0-5 是毫安组（5/10/20/50/100/200 mA），乘 0.01 换算到安培是正常逻辑；索引 ≥6 落在 A 组表（0.5-20 A），不经过该乘法（`fmul [eax*8+0x34d1840]` 与 A 表连续拼接）。NOP 掉这条指令会在仪器真正处于毫安档时把轴放大 100 倍。先前的"根因 = atoi 型号分类错误导致 ×0.01"分析作废。

**实际根因（实测证据，Windows 10 22H2 + WT210 + 82357B，原版 exe + 修补 tmctl.dll）**：

1. 轴刻度 = 3 × A表[存储的量程索引]（`getARange`，VA 0x158c6f0；型号 6 的 A 表在 0x34d1870 = [0.5, 1, 2, 5, 10, 20]）。±15.00m 即索引 0（'5 mA'）；仪器 AUTO 解析在 0.5 A 时正确索引应为 6。
2. 连接后内存实读（元素记录，步长 0x90）：A 索引 = 0，V 索引 = 4（300 V，正确）——连接流程对 V 落库、对 A 不落库，不对称。
3. 量程解析函数本身没有问题（虚方法 vtable+0x178，VA 0xd67370）：对 `500.0E-03`、`1.0000E+00` 等 E 记法与任意小数位都能正确得到数值索引（40 项双拼写表数值化比较），Config 变更路径实测 '500.0E-03' → 索引 6。
4. 缺陷在调用语义：连接路径走"设置+验证"方法（VA 0xd67630）——AUTO 模式下验证时把量程当作 12（combo 的 AUTO 位置），既不查询 AUTO 实际解析出的数值量程，也不写元素记录；唯一会把解析结果写进记录的同步调用（VA 0x1576c55，以记录指针 &flag38/&A_idx 为参数）只在 Config 对话框发生真实变化时触发。
5. 稳态轮询只查 `:CONFigure:CURRent:AUTO?` / `:VOLTage:AUTO?` 布尔值（调用点 VA 0xd675c2 / 0xd67092，约 1.3 s 周期），从不轮询 `RANGe?`——仪器 AUTO 自动降档/升档时软件无从感知，轴不会跟随。
6. 与 `tmctl.dll` 取样补丁无关：换回原版（未修补）tmctl.dll 后连接，轴同样显示 ±15.00m（实机复现）；修补版下连接后内存实读 A 索引同样为 0。缺陷在 WtViewer.exe 自身的连接路径。

**临时方案**（每次启动后如需正确显示）：打开 Config → A 量程先选 **0.5 A** → OK → 再打开 Config → 选回 **AUTO** → OK。第二步必须发生真实变化才会触发记录同步（对原值重选是空操作）。手动界限模式不受影响。

**修复方向**：在 A-AUTO 轮询点（VA 0xd675c2 所在调用）追加一次记录同步调用 `fnB(控制器this, 0, 0, &flag38, &A_idx)`（this 与记录地址运行时捕获），可同时解决连接后索引为 0 与 AUTO 档位不跟随两个问题；frida 侧车或 exe 代码洞注入（同 `wt-patch-tmctl.py` 手法）均可实现。待实施。

## 原因与验证

原版分段接收 `:MEASure:BINary?` 的响应。读取 `#5` 后，下一次 `RcvRespMsg` 返回 `EADR`（3），后续查询触发仪器的 `410, Query INTERRUPTED`。补丁在该 GPIB 二进制读取路径上一次接收完整响应，按块头中的长度将数据交给 WTViewer。

实机复测连续运行 24 秒，CSV 记录 48 条电压、电流和功率数据。重复 Start → Stop 和单次 Update 均通过。其他型号、波形和谐波采集尚未验证。

`wt-acceptance.py` 是 Windows 实机测试脚本。它将连接仪器、运行两轮 Start/Stop 和一次 Update，并校验 CSV。测试前请在 WTViewer 中设好 GPIB 地址 1 和可写的自动保存目录，并关闭其他访问仪器的程序。

```powershell
py .\wt-acceptance.py "C:\WTViewerWin10\WtViewer.exe" "C:\WTViewerWin10\Data"
```
