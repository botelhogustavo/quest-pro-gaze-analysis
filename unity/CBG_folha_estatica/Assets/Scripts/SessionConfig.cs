using System.IO;
using System.Text;
using UnityEngine;

public static class SessionConfig
{
    public static string ParticipantId = "P00";

    public static void Load()
    {
        string path = Path.Combine(Application.persistentDataPath, "config.txt");
        if (!File.Exists(path))
            File.WriteAllText(path, "participant=P00\n");

        foreach (string line in File.ReadAllLines(path))
        {
            string trimmed = line.Trim();
            if (trimmed.Length == 0 || trimmed.StartsWith("#")) continue;

            string[] parts = trimmed.Split(new[] { '=' }, 2);
            if (parts.Length != 2) continue;

            if (parts[0].Trim().ToLower() == "participant")
            {
                string value = Sanitize(parts[1]);
                if (value.Length > 0) ParticipantId = value;
            }
        }

        Debug.Log($"SessionConfig: participant={ParticipantId} (from {path})");
    }

    static string Sanitize(string s)
    {
        var sb = new StringBuilder();
        foreach (char c in s.Trim())
            if (char.IsLetterOrDigit(c) || c == '-' || c == '_') sb.Append(c);
        return sb.ToString();
    }
}