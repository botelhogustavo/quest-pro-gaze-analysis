using System;
using System.IO;
using System.Text;
using UnityEngine;

public class GazeLogger : MonoBehaviour
{
    public OVREyeGaze eyeGaze;
    public Collider panel;
    public bool useMouseInEditor = true;   // test without a headset

    [Header("Fallback (test only)")]
    public bool headFallback = false;      // if eye tracking fails, use head direction (confidence = 0)

    [Header("Diagnostics (temporary)")]
    // Adds columns: dir_x,dir_y,dir_z (gaze direction, world) and angle_deg
    // (angle between the gaze ray and the panel centre). Turn off after debugging.
    public bool logDiagnostics = true;

    [Header("Beeps")]
    public bool playBeeps = true;
    [Range(0f, 1f)] public float beepVolume = 0.5f;

    [Header("Gaze dot (prototyping only)")]
    public GameObject dot;                 // drag the GazeDot sphere from the scene here
    public bool showDot = true;            // turn off for real sessions
    public float dotSize = 0.015f;         // meters (1.5 cm)

    StringBuilder sb;
    string path;
    bool recording = false;
    float t0;

    AudioSource audioSource;
    AudioClip startClip;
    AudioClip stopClip;

    void Start()
    {
        SessionConfig.Load();
        InitLogPath();

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
    }

    void InitLogPath()
    {
        string fileName = $"gaze_{SessionConfig.ParticipantId}_{SessionConfig.ExerciseId}_{DateTime.Now:yyyyMMdd_HHmmss}.csv";

#if UNITY_ANDROID && !UNITY_EDITOR
        string publicFolder = "/storage/emulated/0/Download";
        if (!Directory.Exists(publicFolder))
        {
            Directory.CreateDirectory(publicFolder);
        }
        path = Path.Combine(publicFolder, fileName);
#else
        path = Path.Combine(Application.persistentDataPath, fileName);
#endif

        string header = "time_s,x,y,confidence,on_panel";
        if (logDiagnostics) header += ",dir_x,dir_y,dir_z,angle_deg";
        sb = new StringBuilder(header + "\n");
        Debug.Log("CSV saved directly to: " + path);
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

    bool TogglePressed()
    {
#if UNITY_EDITOR
        if (useMouseInEditor) return Input.GetKeyDown(KeyCode.Space);
#endif
        return OVRInput.GetDown(OVRInput.Button.One);   // A button, right controller
    }

    bool DotTogglePressed()
    {
#if UNITY_EDITOR
        if (useMouseInEditor) return Input.GetKeyDown(KeyCode.D);
#endif
        return OVRInput.GetDown(OVRInput.Button.Four);  // Y button, left controller
    }

    bool TryGetRay(out Ray ray, out float confidence)
    {
#if UNITY_EDITOR
        if (useMouseInEditor)
        {
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
            confidence = 0f;   // 0 = head direction, not eyes
            return true;
        }
        return false;
    }

    void Update()
    {
        if (TogglePressed())
        {
            recording = !recording;
            if (recording)
            {
                InitLogPath();
                t0 = Time.time;
                sb.AppendLine("# start");
                Beep(startClip);
            }
            else
            {
                Save();
                Beep(stopClip);
            }
        }

        if (DotTogglePressed()) showDot = !showDot;

#if !UNITY_EDITOR
        // B button: save (if recording) and close the app
        if (OVRInput.GetDown(OVRInput.Button.Two))
        {
            if (recording) { recording = false; Save(); }
            Application.Quit();
        }
#endif

        RaycastHit hit = default;
        bool hasRay = TryGetRay(out Ray ray, out float conf);
        bool hitPanel = hasRay && panel != null && panel.Raycast(ray, out hit, 10f);

        // Dot: follows the gaze on the panel, hidden when off-panel or tracking is lost
        if (dot != null)
        {
            bool visible = showDot && hitPanel;
            if (dot.activeSelf != visible) dot.SetActive(visible);
            if (visible) dot.transform.position = hit.point + hit.normal * 0.002f;
        }

        if (!recording || !hasRay) return;

        float t = Time.time - t0;

        // Diagnostics: where is the ray pointing relative to the panel?
        string diag = "";
        if (logDiagnostics)
        {
            Vector3 d = ray.direction;
            float angle = panel != null
                ? Vector3.Angle(ray.direction, panel.bounds.center - ray.origin)
                : float.NaN;
            diag = FormattableString.Invariant($",{d.x:F3},{d.y:F3},{d.z:F3},{angle:F1}");
        }

        // FormattableString.Invariant: always '.' as decimal separator, whatever the headset locale
        if (hitPanel)
        {
            // World hit point -> panel local space. Assumes a Unity Quad (local range -0.5..0.5),
            // so +0.5 gives normalised 0..1 with origin at the bottom-left corner.
            Vector3 localPoint = panel.transform.InverseTransformPoint(hit.point);
            float normX = localPoint.x + 0.5f;
            float normY = localPoint.y + 0.5f;

            sb.AppendLine(FormattableString.Invariant($"{t:F4},{normX:F4},{normY:F4},{conf:F2},1") + diag);
        }
        else
        {
            sb.AppendLine(FormattableString.Invariant($"{t:F4},,,{conf:F2},0") + diag);
        }
    }

    void OnApplicationPause(bool paused) { if (paused && recording) Save(); }
    void OnApplicationQuit() { if (recording) Save(); }
    void Save() { File.WriteAllText(path, sb.ToString()); Debug.Log("CSV saved to: " + path); }
}