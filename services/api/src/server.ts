import { createApp } from './app.js'
import type { RuntimeMode } from './runtime.js'

const port = process.env.PORT || 4000
const mode: RuntimeMode = process.env.SKILLTWIN_RUNTIME_MODE === 'mock' ? 'mock' : 'production'
const app = createApp({ mode })

app.listen(port, () => {
  console.log(JSON.stringify({ event: 'api.started', mode, port: Number(port) }))
})
