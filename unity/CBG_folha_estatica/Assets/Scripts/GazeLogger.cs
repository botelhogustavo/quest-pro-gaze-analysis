using System;
using System.IO;
using System.Text;
using UnityEngine;

public class GazeLogger : MonoBehaviour
{
    public OVREyeGaze eyeGaze;
    public Collider panel;
    public bool useMouseInEditor = true;

    [Header("Exercises")]
    public Renderer panelRenderer;          // renderer of the panel (its material texture is swapped)
    public Texture[] exerciseTextures;      // one texture per exercise, in order
    public string[] exerciseNames;          // optional, same order; defaults to the texture name, then ex01, ex02...
    public bool allowPrevious = true;       // X goes back one exercise

    [Header("Session")]
    public float quitHoldSeconds = 2f;      // hold B this long to save and quit
    public float flushIntervalSeconds = 2f; // how often the CSV is flushed to disk

    [Header("Fallback (test only)")]
    public bool headFallback = false;

    [Header("Diagnostics (temporary)")]
    public bool logDiagnostics = false;

    [Header("Beeps")]
    public bool playBeeps = true;
    [Range(0f, 1f)] public float beepVolume = 0.5f;

    [Header("Gaze dot (prototyping only)")]
    public GameObject dot;
    public bool showDot = true;
    public float dotSize = 0.015f;

    StreamWriter writer;
    string path;
    float t0;
    float lastFlush;
    float quitHeld;
    int exerciseIndex;
    string currentExercise = "ex01";
    bool closed;

    AudioSource audioSource;
    AudioClip startClip;
    AudioClip stopClip;

    void Start()
    {
        SessionConfig.Load();
        #if !UNITY_EDITOR
            if (OVRManager.instance == null)
                Debug.LogError("GazeLogger: no OVRManager in the scene, so OVRInput will not update and no button will work.");
        #endif
        audioSource = gameObject.AddComponent<AudioSource>();
        audioSource.spatialBlend = 0f;
        startClip = MakeBeep(880f, 0.15f);
        stopClip = MakeBeep(440f, 0.30f);

        if (dot != null)
        {
            dot.transform.localScale = Vector3.one * dotSize;
            dot.SetActive(false);
        }
        else
        {
            Debug.LogWarning("GazeLogger: 'Dot' field is empty, no gaze dot will be shown.");
        }

        OpenLog();
        ShowExercise(0);
        Beep(startClip);
    }

    void OpenLog()
    {
        string fileName = $"gaze_{SessionConfig.ParticipantId}_{DateTime.Now:yyyyMMdd_HHmmss}.csv";

        path = Path.Combine(Application.persistentDataPath, fileName);   // padrão seguro

        #if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                string publicFolder = "/storage/emulated/0/Download";
                string downloadPath = Path.Combine(publicFolder, fileName);
                writer = new StreamWriter(downloadPath, false, new UTF8Encoding(false));
                path = downloadPath;
            }
            catch (Exception e)
            {
                Debug.LogError("Download FALHOU, usando persistentDataPath: " + e);
            }
        #endif

        if (writer == null)
            writer = new StreamWriter(path, false, new UTF8Encoding(false));

        string header = "time_s,x,y,confidence,on_panel,exercise";
        if (logDiagnostics) header += ",dir_x,dir_y,dir_z,angle_deg";
        writer.WriteLine(header);
        writer.WriteLine("# start");

        t0 = Time.time;
        lastFlush = Time.unscaledTime;
        Debug.Log("Logging to: " + path);
    }

    void CloseLog()
    {
        if (closed || writer == null) return;
        closed = true;
        writer.WriteLine(FormattableString.Invariant($"# end,{Time.time - t0:F4}"));
        writer.Flush();
        writer.Close();
        writer = null;
        Debug.Log("CSV saved to: " + path);
    }

    int ExerciseCount()
    {
        if (exerciseTextures != null && exerciseTextures.Length > 0) return exerciseTextures.Length;
        if (exerciseNames != null && exerciseNames.Length > 0) return exerciseNames.Length;
        return 1;
    }

    string ExerciseName(int i)
    {
        string n = (exerciseNames != null && i < exerciseNames.Length) ? exerciseNames[i] : null;
        if (string.IsNullOrWhiteSpace(n) && exerciseTextures != null
            && i < exerciseTextures.Length && exerciseTextures[i] != null)
            n = exerciseTextures[i].name;
        if (string.IsNullOrWhiteSpace(n)) n = $"ex{i + 1:00}";
        return Sanitize(n);
    }

    static string Sanitize(string s)
    {
        var b = new StringBuilder();
        foreach (char c in s.Trim())
            b.Append(char.IsLetterOrDigit(c) || c == '-' || c == '_' ? c : '_');
        return b.ToString();
    }

    void ShowExercise(int index)
    {
        exerciseIndex = index;
        currentExercise = ExerciseName(index);

        if (panelRenderer == null)
        {
            Debug.LogWarning("GazeLogger: 'Panel Renderer' is empty, texture will not change.");
        }
        else if (exerciseTextures == null || index >= exerciseTextures.Length || exerciseTextures[index] == null)
        {
            Debug.LogWarning($"GazeLogger: no texture assigned for exercise index {index}.");
        }
        else
        {
            Material m = panelRenderer.material;
            Texture tex = exerciseTextures[index];
            if (m.HasProperty("_BaseMap")) m.SetTexture("_BaseMap", tex);
            if (m.HasProperty("_MainTex")) m.SetTexture("_MainTex", tex);
            Debug.Log($"GazeLogger: texture set to {tex.name} (shader: {m.shader.name})");
        }

        if (writer != null)
            writer.WriteLine(FormattableString.Invariant($"# exercise,{Time.time - t0:F4},{currentExercise}"));
    }

    void ChangeExercise(int index)
    {
        Debug.Log($"GazeLogger: change to {index}, current={exerciseIndex}, total={ExerciseCount()}, textures={(exerciseTextures == null ? -1 : exerciseTextures.Length)}, names={(exerciseNames == null ? -1 : exerciseNames.Length)}", this);
        int clamped = Mathf.Clamp(index, 0, ExerciseCount() - 1);
        if (clamped == exerciseIndex)
        {
            Beep(stopClip);   // already at the first/last exercise
            return;
        }
        ShowExercise(clamped);
        Beep(startClip);
    }

    AudioClip MakeBeep(float frequency, float duration)
    {
        int sampleRate = 44100;
        int samples = Mathf.CeilToInt(sampleRate * duration);
        float[] data = new float[samples];
        for (int i = 0; i < samples; i++)
        {
            float envelope = Mathf.Min(1f, Mathf.Min(i, samples - i) / (0.01f * sampleRate));
            data[i] = Mathf.Sin(2f * Mathf.PI * frequency * i / sampleRate) * envelope;
        }
        AudioClip clip = AudioClip.Create("beep", samples, 1, sampleRate, false);
        clip.SetData(data, 0);
        return clip;
    }

    void Beep(AudioClip clip)
    {
        if (playBeeps && audioSource != null) audioSource.PlayOneShot(clip, beepVolume);
    }

    bool NextPressed()
    {
    #if UNITY_EDITOR
        if (useMouseInEditor) return Input.GetKeyDown(KeyCode.Space);
    #endif
        return OVRInput.GetDown(OVRInput.RawButton.A, OVRInput.Controller.RTouch);   // A
    }

    bool PreviousPressed()
    {
    #if UNITY_EDITOR
        if (useMouseInEditor) return Input.GetKeyDown(KeyCode.Backspace);
    #endif
        return OVRInput.GetDown(OVRInput.RawButton.X, OVRInput.Controller.LTouch);   // X
    }

    bool DotTogglePressed()
    {
    #if UNITY_EDITOR
        if (useMouseInEditor) return Input.GetKeyDown(KeyCode.D);
    #endif
        return OVRInput.GetDown(OVRInput.RawButton.Y, OVRInput.Controller.LTouch);   // Y
    }

    void HandleQuit()
    {
    #if !UNITY_EDITOR
        if (OVRInput.Get(OVRInput.RawButton.B, OVRInput.Controller.RTouch))   // B
        {
            quitHeld += Time.unscaledDeltaTime;
            if (quitHeld >= quitHoldSeconds)
            {
                CloseLog();
                Application.Quit();
            }
        }
        else
        {
            quitHeld = 0f;
        }
    #endif
    }

    bool TryGetRay(out Ray ray, out float confidence)
    {
        #if UNITY_EDITOR
            if (useMouseInEditor)
            {
                if (Camera.main == null) { ray = default; confidence = 0f; return false; }
                ray = Camera.main.ScreenPointToRay(Input.mousePosition);
                confidence = 1f;
                return true;
            }
        #endif
        ray = default;
        confidence = 0f;

        if (eyeGaze != null && eyeGaze.EyeTrackingEnabled)
        {
            ray = new Ray(eyeGaze.transform.position, eyeGaze.transform.forward);
            confidence = eyeGaze.Confidence;
            return true;
        }

        if (headFallback && Camera.main != null)
        {
            ray = new Ray(Camera.main.transform.position, Camera.main.transform.forward);
            confidence = 0f;
            return true;
        }
        return false;
    }

    void Update()
    {
        if (Time.frameCount % 60 == 0)
        Debug.Log($"DIAG writer={(writer != null)} active={OVRInput.GetActiveController()} " + $"connected={OVRInput.GetConnectedControllers()} " + $"A={OVRInput.Get(OVRInput.RawButton.A)} mgr={(OVRManager.instance != null)}");

        if (closed) return;

        if (NextPressed()) ChangeExercise(exerciseIndex + 1);
        else if (allowPrevious && PreviousPressed()) ChangeExercise(exerciseIndex - 1);

        if (DotTogglePressed()) showDot = !showDot;

        HandleQuit();
        if (closed) return;

        RaycastHit hit = default;
        bool hasRay = TryGetRay(out Ray ray, out float conf);
        bool hitPanel = hasRay && panel != null && panel.Raycast(ray, out hit, 10f);

        if (dot != null)
        {
            bool visible = showDot && hitPanel;
            if (dot.activeSelf != visible) dot.SetActive(visible);
            if (visible) dot.transform.position = hit.point + hit.normal * 0.002f;
        }

        if (!hasRay || writer == null) return;

        float t = Time.time - t0;

        string diag = "";
        if (logDiagnostics)
        {
            Vector3 d = ray.direction;
            float angle = panel != null
                ? Vector3.Angle(ray.direction, panel.bounds.center - ray.origin)
                : float.NaN;
            diag = FormattableString.Invariant($",{d.x:F3},{d.y:F3},{d.z:F3},{angle:F1}");
        }

        if (hitPanel)
        {
            Vector3 localPoint = panel.transform.InverseTransformPoint(hit.point);
            float normX = localPoint.x + 0.5f;
            float normY = localPoint.y + 0.5f;
            writer.WriteLine(FormattableString.Invariant(
                $"{t:F4},{normX:F4},{normY:F4},{conf:F2},1,{currentExercise}") + diag);
        }
        else
        {
            writer.WriteLine(FormattableString.Invariant(
                $"{t:F4},,,{conf:F2},0,{currentExercise}") + diag);
        }

        if (Time.unscaledTime - lastFlush >= flushIntervalSeconds)
        {
            writer.Flush();
            lastFlush = Time.unscaledTime;
        }
    }

    void OnApplicationPause(bool paused)
    {
        if (writer == null) return;
        string kind = paused ? "pause" : "resume";
        writer.WriteLine(FormattableString.Invariant($"# {kind},{Time.time - t0:F4}"));
        if (paused) writer.Flush();
    }

    void OnApplicationQuit() { CloseLog(); }
    void OnDestroy() { CloseLog(); }
}