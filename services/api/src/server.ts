import { createApp } from './app.js'

const port = process.env.PORT || 4000
const app = createApp()

app.listen(port, () => {
  console.log(`SkillTwin mock API server running on port ${port}`)
})
