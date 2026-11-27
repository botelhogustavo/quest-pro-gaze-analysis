using System.IO;
using UnityEngine;

public static class SessionConfig
{
    public static string ParticipantId = "P00";
    public static string ExerciseId = "ex00";

    public static void Load()
    {
        string path = Path.Combine(Application.persistentDataPath, "config.txt");
        if (!File.Exists(path))
            File.WriteAllText(path, "participant=P00\nexercise=ex00\n");

        foreach (string line in File.ReadAllLines(path))
        {
            string trimmed = line.Trim();
            if (trimmed.Length == 0 || trimmed.StartsWith("#")) continue;

            string[] parts = trimmed.Split(new[] { '=' }, 2);
            if (parts.Length != 2) continue;

            string key = parts[0].Trim().ToLower();
            string value = Sanitize(parts[1]);
            if (value.Length == 0) continue;

            if (key == "participant") ParticipantId = value;
            else if (key == "exercise") ExerciseId = value;
        }

        Debug.Log($"SessionConfig: participant={ParticipantId}, exercise={ExerciseId} (from {path})");
    }

    // Keeps only letters, digits, '-' and '_' so the value is safe in a file name
    static string Sanitize(string s)
    {
        var sb = new System.Text.StringBuilder();
        foreach (char c in s.Trim())
            if (char.IsLetterOrDigit(c) || c == '-' || c == '_') sb.Append(c);
        return sb.ToString();
    }
}