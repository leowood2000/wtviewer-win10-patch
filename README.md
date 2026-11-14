# WTViewer 8.24 Win10 补丁

在 Windows 10 22H2 x64 上修复横河 WTViewer 8.24 通过 Agilent 82357B 采集 WT210 普通测量数据时遇到的 Start 无读数和 Stop 卡死问题。需要已有的 WTViewer 安装和可用的 GPIB 环境。

## 生成和使用

1. 将现有 WTViewer 安装目录完整复制到可写目录，例如 `C:\WTViewerWin10`。
2. 在本仓库目录运行以下命令。将路径换成你的实际目录。

   ```powershell
   py -m pip install -r requirements.txt
   py .\wt-patch-tmctl.py "C:\Program Files (x86)\Yokogawa\WTViewer\tmctl.dll" "C:\WTViewerWin10\tmctl.dll"
   ```

3. 从副本启动 `WtViewer.exe`，选择 On-Line、GPIB 和 Normal Measurement。仪器需设为 488.2 模式，地址与软件中的设置一致。本机验证使用地址 1。需要保存时，在数值窗口启用 Auto Saving 并选可写的 CSV 路径。
4. 双击原安装目录中的程序可回到原版。也可把原版 DLL 重新复制到应用副本。

补丁生成器适配 SHA-256 为 `5bc57668140e6d075acdbab12f2a979594b5b5aa5d173b948745d2bcB2bbfd01` 的 `tmctl.dll` 2.1.6.0。仓库提供生成脚本，原版与修补后的 DLL 都在本机保管。

## Auto Ranging 显示修复（WT210 电流轴）

**症状**：Wave 窗口 Wave Detail 勾选 Auto Ranging 后，I1 电流轴刻度只有 ±15.00m（0.015 A），波形压成平线；改手动界限则显示正常。V1 电压轴不受影响。

**根因**：实测 WT210 的 `*IDN?` 应答第 2 字段是产品码 `760401`。WTViewer 连接时用 `atoi` 解析该字段并查表分类（VA 0x159c5c0）：`760401` 被映射到内部型号枚举 6，后续一切按外置电流传感器输入的机型处理（按字符串表推断为 WT110 一类）。电流显示量程函数 getARange（VA 0x158c6f0）在型号 5/6 且量程索引 < 6 时把结果再乘 0.01：

```
A = CT(1.0) × A表[0]=0.5 × 0.01 = 0.005 → 轴 = 0.005 × 3 = ±0.015
```

WT210 直连输入没有这层 0.01，电流轴因此缩小 100 倍。电压路径 getVRange（VA 0x158c4b0）没有此乘法，所以电压轴一直正确。

**补丁**：把 VA 0x158c975 处的 `fmul qword ptr [0x1624a48]`（6 字节 `DC 0D 48 4A 62 01`）替换为 6 个 NOP，去掉型号 5/6 分支的 ×0.01。该指令后紧跟函数收尾，NOP 不影响型号 2/3/4/7/8 和量程索引 ≥ 6 的其他分支。

```powershell
py .\wt-patch-autoscale.py "C:\Program Files (x86)\Yokogawa\WTViewer\WtViewer.exe" "C:\WTViewerWin10\WtViewer.exe"
```

适配 SHA-256 为 `ebc1ce26fb83a6c781d2d37e6acc862376e5ee26e1da1b67055f6e4de6f15c11` 的 `WtViewer.exe`（WTViewer 8.24）。替换文件前先关闭正在运行的 WTViewer。

**验证**（实机 WT210，300 V 手动量程 / 0.5 A AUTO，谐波测量模式）：补丁后 Auto Ranging ON 时 I1 轴显示 ±1.500 A（补丁前 ±15.00m），V1 轴 ±900.0 不变；电压、电流、功率、PF、THD 等测量数据与补丁前一致。

**注意**：型号 5/6 的 ×0.01 是为外置电流传感器输入设计的缩放，用传感器接这类机型时不要打此补丁；本补丁只面向 WT210 直连输入的用法。它与 tmctl 取样补丁相互独立，可单独或一起使用。

## 原因与验证

原版分段接收 `:MEASure:BINary?` 的响应。读取 `#5` 后，下一次 `RcvRespMsg` 返回 `EADR`（3），后续查询触发仪器的 `410, Query INTERRUPTED`。补丁在该 GPIB 二进制读取路径上一次接收完整响应，按块头中的长度将数据交给 WTViewer。

实机复测连续运行 24 秒，CSV 记录 48 条电压、电流和功率数据。重复 Start → Stop 和单次 Update 均通过。其他型号、波形和谐波采集尚未验证。

`wt-acceptance.py` 是 Windows 实机测试脚本。它将连接仪器、运行两轮 Start/Stop 和一次 Update，并校验 CSV。测试前请在 WTViewer 中设好 GPIB 地址 1 和可写的自动保存目录，并关闭其他访问仪器的程序。

```powershell
py .\wt-acceptance.py "C:\WTViewerWin10\WtViewer.exe" "C:\WTViewerWin10\Data"
```
