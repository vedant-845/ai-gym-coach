# 🏋️ AI Real-time Gym Coach

A real-time workout coach that uses your webcam to track your form, count reps, and give spoken feedback while you exercise.

## 🔗 Live Demo

| | Link |
|---|---|
| 🌐 **Landing Page** | [loquacious-meerkat-742365.netlify.app](https://loquacious-meerkat-742365.netlify.app) |
| 🚀 **Live App** | [Try the AI Gym Coach](https://ai-gym-coach-ggwktcc58qz2vuwqlhkrd6.streamlit.app/) |

> Allow camera access when your browser asks. If the app is asleep, click the "wake up" button and wait a few seconds.

## ✨ Features

- **Real-time pose detection** with MediaPipe and OpenCV
- **Rep and set counting** for your chosen workout plan
- **Live form metrics**, such as joint angles, body alignment and balance
- **AI voice coaching:** an LLM writes short coaching feedback and text-to-speech reads it out loud
- **Workout history** saved per user, with a login system
- **Supported exercises:** Squats, Push-ups, Biceps Curls (Dumbbell), Shoulder Press, Lunges

## 🛠️ Tech Stack

| Area | Tools |
|---|---|
| App framework | Streamlit, streamlit-webrtc |
| Computer vision | MediaPipe, OpenCV |
| AI coaching | Groq API (LLM) |
| Voice | gTTS |
| Data | SQLite, pandas |
| Landing page | HTML, CSS, JavaScript (hosted on Netlify) |

## 📁 Project Structure

```
ai-gym-coach/
├── LandingPage/        # Static website (deployed on Netlify)
├── Main App/           # Streamlit app
│   ├── main.py         # App entry point
│   ├── core/
│   ├── detectors/      # Exercise detection logic
│   ├── ml_models/
│   ├── pages/
│   ├── services/       # Auth, coaching (LLM + TTS), tracking, storage
│   └── static/         # CSS and fonts
├── requirements.txt
└── packages.txt
```

## 🚀 Run Locally

**1. Clone the repository**

```bash
git clone https://github.com/vedant-845/ai-gym-coach.git
cd ai-gym-coach
```

**2. Install dependencies** (Python 3.11 or 3.12 recommended)

```bash
pip install -r requirements.txt
```

Or with [uv](https://github.com/astral-sh/uv):

```bash
uv sync
```

**3. Add your Groq API key**

Get a free key at [console.groq.com/keys](https://console.groq.com/keys), then create `.streamlit/secrets.toml`:

```toml
GROQ_API_KEY = "your_key_here"
```

Or set it as an environment variable:

```bash
# Windows PowerShell
$env:GROQ_API_KEY="your_key_here"

# macOS / Linux
export GROQ_API_KEY="your_key_here"
```

**4. Start the app**

```bash
streamlit run "Main App/main.py"
```

Open http://localhost:8501 in your browser.

## ☁️ Deployment

- **App:** Streamlit Community Cloud, with `GROQ_API_KEY` added under the app's **Secrets** settings
- **Landing page:** Netlify, with the publish directory set to `LandingPage`

## 📝 Notes

- The camera only works on `localhost` or HTTPS.
- Never commit `.streamlit/secrets.toml` or your API key to GitHub.
- On the free cloud tier the SQLite database is not permanent, so accounts and history may reset when the app restarts.

## 👤 Author

**Vedant Chaudhari**

- LinkedIn: [vedant-chaudhari](https://www.linkedin.com/in/vedant-chaudhari-853229322/)
- GitHub: [@vedant-845](https://github.com/vedant-845)
- Email: vedant9748@gmail.com