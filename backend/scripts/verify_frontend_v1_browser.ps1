# 使用 Windows Chrome 调试接口模拟新版前端完整用户操作，并保存报告页截图。
$ErrorActionPreference = "Stop"
$debugPort = if ($env:ARCHCRITIC_CHROME_DEBUG_PORT) { $env:ARCHCRITIC_CHROME_DEBUG_PORT } else { "9223" }
$frontendUrl = if ($env:ARCHCRITIC_FRONTEND_URL) { $env:ARCHCRITIC_FRONTEND_URL } else { "http://localhost:4174/" }
$screenshotPath = if ($env:ARCHCRITIC_SCREENSHOT) { $env:ARCHCRITIC_SCREENSHOT } else { "C:\Windows\Temp\archcritic-report.png" }

# 新建 Chrome 标签页并连接调试 WebSocket。
$target = Invoke-RestMethod -Method Put -Uri "http://127.0.0.1:$debugPort/json/new?$frontendUrl"
$socket = [Net.WebSockets.ClientWebSocket]::new()
$socket.ConnectAsync([Uri]$target.webSocketDebuggerUrl, [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
$script:nextId = 1

# 调用一条 Chrome DevTools 命令并等待结果。
function Invoke-Cdp([string]$method, [hashtable]$params = @{}) {
    $callId = $script:nextId
    $script:nextId += 1
    $payload = @{ id = $callId; method = $method; params = $params } | ConvertTo-Json -Compress -Depth 20
    $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
    $segment = [ArraySegment[byte]]::new($bytes)
    $socket.SendAsync($segment, [Net.WebSockets.WebSocketMessageType]::Text, $true, [Threading.CancellationToken]::None).GetAwaiter().GetResult() | Out-Null
    while ($true) {
        $stream = [IO.MemoryStream]::new()
        do {
            $buffer = New-Object byte[] 65536
            $result = $socket.ReceiveAsync([ArraySegment[byte]]::new($buffer), [Threading.CancellationToken]::None).GetAwaiter().GetResult()
            $stream.Write($buffer, 0, $result.Count)
        } while (-not $result.EndOfMessage)
        $message = [Text.Encoding]::UTF8.GetString($stream.ToArray()) | ConvertFrom-Json
        if ($message.id -eq $callId) {
            if ($message.error) { throw ($message.error | ConvertTo-Json -Compress) }
            return $message.result
        }
    }
}

# 在当前页面执行 JavaScript。
function Invoke-JavaScript([string]$expression) {
    $response = Invoke-Cdp "Runtime.evaluate" @{ expression = $expression; returnByValue = $true; awaitPromise = $true }
    if ($response.exceptionDetails) { throw ($response.exceptionDetails | ConvertTo-Json -Compress) }
    return $response.result.value
}

# 等待页面条件成立。
function Wait-Page([string]$expression, [int]$timeoutSeconds = 8) {
    $deadline = [DateTime]::UtcNow.AddSeconds($timeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Invoke-JavaScript $expression) { return }
        Start-Sleep -Milliseconds 200
    }
    throw "等待页面状态超时：$expression"
}

# 点击包含指定文字的首个按钮。
function Click-Text([string]$text) {
    $jsonText = $text | ConvertTo-Json -Compress
    $clicked = Invoke-JavaScript "(() => { const button = [...document.querySelectorAll('button')].find(item => item.textContent.includes($jsonText)); if (!button) return false; button.click(); return true; })()"
    if (-not $clicked) { throw "未找到按钮：$text" }
}

# 填写输入框或多行文本框，并触发 React 更新。
function Set-Control([string]$selector, [int]$index, [string]$value) {
    $jsonSelector = $selector | ConvertTo-Json -Compress
    $jsonValue = $value | ConvertTo-Json -Compress
    $updated = Invoke-JavaScript "(() => { const item = document.querySelectorAll($jsonSelector)[$index]; if (!item) return false; const prototype = item.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype; Object.getOwnPropertyDescriptor(prototype, 'value').set.call(item, $jsonValue); item.dispatchEvent(new Event('input', { bubbles: true })); return true; })()"
    if (-not $updated) { throw "未找到表单控件：$selector[$index]" }
}

# 跳转到指定前端路由。
function Set-Route([string]$name) {
    Invoke-JavaScript "window.location.hash = '/$name'" | Out-Null
    Wait-Page "window.location.hash === '#/$name'"
    Start-Sleep -Milliseconds 300
}

# 执行浏览器级完整交互验收。
$checks = 0
Invoke-Cdp "Emulation.setDeviceMetricsOverride" @{ width = 1536; height = 820; deviceScaleFactor = 1; mobile = $false } | Out-Null
Wait-Page "document.readyState === 'complete'"
Start-Sleep -Milliseconds 500
Set-Route "info"
Wait-Page "document.querySelectorAll('input').length >= 4"
Set-Control "input" 0 "浏览器验收项目"
Set-Control "textarea" 0 "公共文化建筑浏览器验收方案，重点关注入口、展厅和后勤流线。"
Click-Text "保存草稿"
Start-Sleep -Milliseconds 800
Click-Text "下一步"
Wait-Page "window.location.hash === '#/agents'"
$checks += 3

Click-Text "下一步"
Wait-Page "window.location.hash === '#/upload'"
Click-Text "下一步"
Wait-Page "window.location.hash === '#/confirm'"
Click-Text "确认提交"
Wait-Page "window.location.hash === '#/processing'"
Start-Sleep -Seconds 2
Click-Text "查看评图报告"
Wait-Page "window.location.hash === '#/report'"
$checks += 5

Click-Text "场地"
Click-Text "查看详情"
Wait-Page "document.body.textContent.includes('专项评图详情')"
Set-Route "report"
$traceClicked = Invoke-JavaScript "(() => { const buttons = [...document.querySelectorAll('button')].filter(item => item.textContent.includes('查看')); const button = buttons.at(-1); if (!button) return false; button.click(); return true; })()"
if (-not $traceClicked) { throw "未找到知识库追溯入口" }
Wait-Page "document.body.textContent.includes('点击空白区域关闭')"
Set-Route "report"
$checks += 5

Set-Control "textarea" 0 "列出必须修改项"
Click-Text "发送"
Wait-Page "document.body.textContent.includes('本轮必须修改项')"
Click-Text "历史版本对比"
Wait-Page "window.location.hash === '#/history'"
Click-Text "返回"
Wait-Page "window.location.hash === '#/report'"
$checks += 5

$screenshot = Invoke-Cdp "Page.captureScreenshot" @{ format = "png" }
[IO.File]::WriteAllBytes($screenshotPath, [Convert]::FromBase64String($screenshot.data))
Write-Output "浏览器交互验收通过：$checks/$checks，截图：$screenshotPath"
