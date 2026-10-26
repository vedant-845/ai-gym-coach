import streamlit as st
import streamlit.components.v1 as components
import base64
import os
import time
import pandas as pd
from services.auth.login_wall import render_login_wall
from services.state.session_defaults import initial_session_defaults
from services.config.workout_config import EXERCISE_OPTIONS
from services.ui.style_loader import load_css, inject_local_font, inject_webrtc_styles
from services.persistence.exercise_repository import init_db
from streamlit_webrtc import webrtc_streamer, WebRtcMode
from services.vision.exercise_video_processor import VideoProcessorClass
from services.tracking.metrics import sync_metrics_update
from services.persistence.exercise_repository import get_users_exercises
from groq import Groq
from services.coaching.llm import LLMCoach
from services.coaching.tts import TextToSpeech
from services.coaching.voice_pipeline import VoicePipeline


def get_groq_api_key() -> str:
    """Read the key from the environment first, then from Streamlit secrets."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if api_key:
        return api_key

    # st.secrets raises if no secrets.toml exists, so guard it.
    try:
        return st.secrets["GROQ_API_KEY"]
    except Exception:
        return ""


def audio_mime(audio_bytes: bytes) -> str:
    """Guess the audio format from the file header (WAV starts with 'RIFF')."""
    if audio_bytes[:4] == b"RIFF":
        return "audio/wav"
    if audio_bytes[:4] == b"OggS":
        return "audio/ogg"
    return "audio/mp3"


def to_audio_bytes(audio):
    """Make sure the audio is raw bytes. Returns None if it can't be used."""
    if audio is None:
        return None
    if isinstance(audio, (bytes, bytearray)):
        return bytes(audio) if len(audio) > 0 else None
    if hasattr(audio, "read"):  # file-like object / BytesIO
        data = audio.read()
        return data if data else None
    if isinstance(audio, str) and os.path.exists(audio):  # file path
        with open(audio, "rb") as f:
            return f.read()
    return None


def play_audio_hidden(audio_bytes: bytes):
    """Play audio automatically with no visible player.

    Uses a tiny iframe that calls .play() itself. If the browser still blocks it,
    the iframe grows a small 'Tap to hear coach' button as a fallback.
    The iframe content only changes when the audio changes, so each coach
    message plays once and is not replayed by the 0.25s rerun loop.
    """
    b64 = base64.b64encode(audio_bytes).decode()
    mime = audio_mime(audio_bytes)

    components.html(
        f"""
        <audio id="coach" autoplay>
            <source src="data:{mime};base64,{b64}" type="{mime}">
        </audio>
        <script>
            const a = document.getElementById("coach");
            const p = a.play();
            if (p !== undefined) {{
                p.catch(function () {{
                    try {{ window.frameElement.style.height = "44px"; }} catch (e) {{}}
                    document.body.innerHTML =
                        '<button id="b" style="padding:8px 14px;border-radius:6px;' +
                        'border:1px solid #888;background:#222;color:#eee;cursor:pointer;">' +
                        '🔊 Tap to hear coach</button>';
                    document.getElementById("b").onclick = function () {{
                        a.play();
                        this.remove();
                        try {{ window.frameElement.style.height = "0px"; }} catch (e) {{}}
                    }};
                    document.body.appendChild(a);
                }});
            }}
        </script>
        """,
        height=0,
    )


def main():
    st.set_page_config(
        page_icon="🏋️‍♀️",
        page_title="AI Real-time GYM Coach",
        initial_sidebar_state="expanded",
        layout="centered"
    )

    load_css(os.path.join(os.getcwd(), "static", "style.css"))
    inject_local_font(os.path.join(os.getcwd(), "static", "AdobeClean.otf"), "AdobeClean")

    init_db()

    if not render_login_wall():
        return

    initial_session_defaults()

    # ---------- Voice pipeline setup (errors are now visible) ----------
    if "voice_pipeline" not in st.session_state:
        try:
            api_key = get_groq_api_key()
            if not api_key:
                raise ValueError(
                    "GROQ_API_KEY not found. Set it as an environment variable "
                    "or in .streamlit/secrets.toml."
                )

            groq_client = Groq(api_key=api_key)
            llm_coach = LLMCoach(groq_client)
            tts = TextToSpeech()
            st.session_state.voice_pipeline = VoicePipeline(llm_coach, tts)
            st.session_state.voice_init_error = None
        except Exception as e:
            st.session_state.voice_pipeline = None
            st.session_state.voice_init_error = f"{type(e).__name__}: {e}"

    workout_started = st.session_state.get("workout_started", False)

    with st.sidebar:
        st.title("🏋️‍♂️ Apna AI Coach")

        if st.session_state.username:
            st.caption(f"👤 Login as {st.session_state.username}")

        if st.session_state.get("voice_pipeline") is None:
            st.warning(
                f"Voice coach disabled: {st.session_state.get('voice_init_error', 'unknown')}"
            )
            if st.button("Retry voice setup", key="retry_voice"):
                del st.session_state["voice_pipeline"]
                st.rerun()

        st.divider()

        st.subheader("Workout Plan")

        if not workout_started:
            plan_exercise = st.selectbox("Exercise", options=EXERCISE_OPTIONS, key="plan_exercise")

            plan_sets = st.number_input("Sets", min_value=0, max_value=50, key="plan_sets", step=1)

            plan_reps = st.number_input("Reps per Set", min_value=0, max_value=50, key="plan_reps", step=1)

            st.markdown("")

            start_session_button = st.button("Start Workout", width="stretch", key="start_session_button")

            if start_session_button:
                st.session_state.exercise_type = plan_exercise
                st.session_state.target_sets = int(plan_sets)
                st.session_state.reps_per_set = int(plan_reps)
                st.session_state.reps = 0
                st.session_state.workout_started = True
                st.session_state.set_cycle_started_at = time.time()
                st.session_state.last_saved_sets_completed = 0

                if st.session_state.voice_pipeline:
                    try:
                        result = st.session_state.voice_pipeline.process_event(
                            event="workout_started",
                            exercise=plan_exercise,
                            metrics={}
                        )
                        if result:
                            st.session_state.audio_to_play, st.session_state.coach_feedback = result
                    except Exception as e:
                        st.session_state.voice_runtime_error = f"{type(e).__name__}: {e}"

                st.session_state.last_notified_sets_completed = 0
                st.session_state.last_notified_workout_complete = False
                st.rerun()
        else:
            exercise = st.session_state.get("exercise_type")
            sets = st.session_state.get("target_sets")
            reps = st.session_state.get("reps_per_set")

            st.info(f"**{exercise}** -- {sets} Sets / {reps} Reps")

            end_session_button = st.button("End Workout", key="end_session_button", width="stretch")

            if end_session_button:
                st.session_state.workout_started = False

                if st.session_state.voice_pipeline:
                    try:
                        result = st.session_state.voice_pipeline.process_event(
                            event="workout_completed",
                            exercise=exercise,
                            metrics={}
                        )
                        if result:
                            st.session_state.audio_to_play, st.session_state.coach_feedback = result
                    except Exception as e:
                        st.session_state.voice_runtime_error = f"{type(e).__name__}: {e}"

                st.rerun()

        if workout_started:
            st.divider()

            exercise = st.session_state.get("exercise_type")
            total_reps = st.session_state.get("reps")
            current_set_reps = st.session_state.get("current_set_reps")
            reps_per_set = st.session_state.get("reps_per_set")
            sets_completed = st.session_state.get("sets_completed")
            target_sets = st.session_state.get("target_sets")

            st.subheader("Progress")

            st.metric("Total Reps", f"{total_reps}")
            st.metric("Current Set Reps", f"{current_set_reps} / {reps_per_set}")
            st.metric("Sets Completed", f"{sets_completed} / {target_sets}")

            st.divider()

            if exercise == "Squats":
                st.subheader("Squat Metrics")
                st.metric("Knee Angle", f"{st.session_state.knee_angle}°")
                st.metric("Back Angle", f"{st.session_state.back_angle}°")
                st.metric("Depth Status", st.session_state.depth_status)

            elif exercise == "Push-ups":
                st.subheader("Push-up Metrics")
                st.metric("Elbow Angle", f"{st.session_state.elbow_angle}°")
                st.metric("Body Alignment", st.session_state.body_alignment)
                st.metric("Hip Position", st.session_state.hip_status)

            elif exercise == "Biceps Curls (Dumbbell)":
                st.subheader("Curl Metrics")
                st.metric("Elbow Angle", f"{st.session_state.elbow_angle}°")
                st.metric("Shoulder Stability", st.session_state.shoulder_status)
                st.metric("Swing Detection", st.session_state.swing_status)

            elif exercise == "Shoulder Press":
                st.subheader("Shoulder Press Metrics")
                st.metric("Elbow Angle", f"{st.session_state.elbow_angle}°")
                st.metric("Arm Extension", st.session_state.extension_status)
                st.metric("Back Arch", st.session_state.back_arch_status)

            elif exercise == "Lunges":
                st.subheader("Lunge Metrics")
                st.metric("Front Knee Angle", f"{st.session_state.front_knee_angle}°")
                st.metric("Torso Angle", f"{st.session_state.torso_angle}°")
                st.metric("Balance Status", st.session_state.balance_status)

    st.title("AI Real-time GYM Coach")
    st.markdown("#### Real-time pose detection with proactive AI voice coaching")

    # ---------- TEMPORARY: voice debug button (remove once audio works) ----------
    with st.expander("🔧 Voice debug", expanded=False):
        if st.button("Test voice", key="test_voice_button"):
            pipeline = st.session_state.get("voice_pipeline")
            st.write("Pipeline:", pipeline)

            if pipeline is None:
                st.error(st.session_state.get("voice_init_error", "Pipeline is None"))
            else:
                try:
                    res = pipeline.process_event(
                        event="workout_started",
                        exercise="Squats",
                        metrics={}
                    )
                    st.write("Result is None?", res is None)

                    if res:
                        test_audio, test_text = res
                        st.write("Text:", test_text)
                        st.write("Audio type:", type(test_audio))

                        test_bytes = to_audio_bytes(test_audio)
                        st.write("Audio size (bytes):", len(test_bytes) if test_bytes else 0)

                        if test_bytes:
                            st.write("Detected format:", audio_mime(test_bytes))
                            st.audio(test_bytes, format=audio_mime(test_bytes))
                        else:
                            st.error("TTS returned no usable audio. Check tts.py.")
                except Exception as e:
                    st.exception(e)

        if st.session_state.get("voice_runtime_error"):
            st.error(f"Last voice error: {st.session_state.voice_runtime_error}")

    # ---------- Coach audio ----------
    # The audio stays in session state and is rendered on every run. Because the
    # element's content doesn't change between reruns, Streamlit keeps the same
    # player in the page, so it plays once and isn't cut off by the 0.25s rerun loop.
    # A new coach message replaces it, which triggers autoplay again.
    audio_bytes = to_audio_bytes(st.session_state.get("audio_to_play"))
    if audio_bytes:
        play_audio_hidden(audio_bytes)

    if st.session_state.get("coach_feedback"):
        st.markdown("")
        st.success(f"🤖 **Coach:** {st.session_state.coach_feedback}")

    if not workout_started:
        st.markdown(
            """
            <div style="
                border: 10px dashed #444;
                border-radius: 0px;
                padding: 48px 32px;
                text-align: center;
                color: #888;
                margin-top: 32px;
                margin-bottom: 32px;
            ">
                <h2 style="color:#ccc; margin-bottom:8px;">👈 Set your workout plan</h2>
                <p style="font-size:1.05rem;">
                    Choose your exercise, sets and reps in the sidebar,<br>
                    then click <strong>Start Workout</strong> to activate the camera and AI coach.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        context = webrtc_streamer(
            key="exercise-analysis",
            mode=WebRtcMode.SENDRECV,
            video_processor_factory=VideoProcessorClass,
            rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
            media_stream_constraints={
                "video": True,
                "audio": False
            },
            async_processing=True
        )

        sync_metrics_update(context)

        if context.state.playing:
            time.sleep(0.25)
            st.rerun()

        inject_webrtc_styles()

    st.divider()

    st.markdown("#### Workout History")

    user_id = st.session_state.get("user_id", 0)

    if isinstance(user_id, int):
        history_rows = get_users_exercises(user_id)

        arr = [
            {
                "Exercise": row['exercise_name'],
                "Reps": row['reps'],
                "Sets": row['sets'],
                "Time (sec)": row['time'],
                "Date": row['created_at']
            }
            for row in history_rows
        ]

        df = pd.DataFrame(arr)

        if not df.empty:
            df["Date"] = pd.to_datetime(df["Date"]).dt.date
            agg_df = df.groupby(["Exercise", "Date"]).agg({
                "Reps": 'sum',
                "Sets": "sum",
                "Time (sec)": "sum"
            }).reset_index()
            agg_df.index += 1
            st.table(agg_df, border="horizontal")
        else:
            st.info("No workout history found.")


if __name__ == "__main__":
    main()





