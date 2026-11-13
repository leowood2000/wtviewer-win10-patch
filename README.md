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

## 原因与验证

原版分段接收 `:MEASure:BINary?` 的响应。读取 `#5` 后，下一次 `RcvRespMsg` 返回 `EADR`（3），后续查询触发仪器的 `410, Query INTERRUPTED`。补丁在该 GPIB 二进制读取路径上一次接收完整响应，按块头中的长度将数据交给 WTViewer。

实机复测连续运行 24 秒，CSV 记录 48 条电压、电流和功率数据。重复 Start → Stop 和单次 Update 均通过。其他型号、波形和谐波采集尚未验证。

`wt-acceptance.py` 是 Windows 实机测试脚本。它将连接仪器、运行两轮 Start/Stop 和一次 Update，并校验 CSV。测试前请在 WTViewer 中设好 GPIB 地址 1 和可写的自动保存目录，并关闭其他访问仪器的程序。

```powershell
py .\wt-acceptance.py "C:\WTViewerWin10\WtViewer.exe" "C:\WTViewerWin10\Data"
```
