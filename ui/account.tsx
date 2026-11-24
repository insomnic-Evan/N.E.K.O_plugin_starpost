import { Button, Card, Page, Stack, Text, useClipboard, useEffect, useState, useToast } from "@neko/plugin-ui"
import type { PluginSurfaceProps } from "@neko/plugin-ui"

type State = {
  botId?: string
  ui_token: string
  revealed?: { botId: string; credential: string; expiresAt?: number }
}

export default function Account(props: PluginSurfaceProps<State>) {
  const state = props.state
  const [value, setValue] = useState("")
  const [busy, setBusy] = useState(false)
  const clipboard = useClipboard()
  const toast = useToast()
  useEffect(() => { setValue("") }, [state.botId])
  useEffect(() => {
    const result = state.revealed
    if (!result || result.botId !== state.botId) return
    setValue(result.credential)
    void clipboard.write(result.credential).then(ok => {
      if (ok) toast.success(result.expiresAt ? "已复制，绑定码十分钟内有效" : "已复制星邮凭据")
      else toast.error("请手动复制显示的凭据")
    }).catch(() => toast.error("请手动复制显示的凭据"))
    void props.api.refresh().catch(() => {})
  }, [state.revealed?.credential, state.botId])
  useEffect(() => {
    if (!value) return
    const timer = setTimeout(() => setValue(""), 60_000)
    return () => clearTimeout(timer)
  }, [value])
  async function reveal() {
    if (busy) return
    setBusy(true)
    setValue("")
    try {
      await props.api.call("show_binding", { ui_token: state.ui_token })
    } catch (error) {
      toast.error(error instanceof Error ? error.message : String(error))
    } finally {
      try { await props.api.refresh() } finally { setBusy(false) }
    }
  }
  return <Page title="星邮账号"><Card title={state.botId ? "星邮 Bot ID · " + state.botId : "尚未登录星邮"}>
    <Stack>{state.botId ? <Button onClick={reveal} disabled={busy}>绑定凭据 · 显示并复制</Button>
      : <Text>按安装指南绑定角色，随后启用星邮。</Text>}
      {value ? <Text>{value}</Text> : null}
    </Stack>
  </Card></Page>
}
