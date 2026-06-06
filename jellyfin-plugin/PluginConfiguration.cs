using MediaBrowser.Model.Plugins;

namespace JellyLogin.Plugin;

/// <summary>
/// Configuration stored by Jellyfin for the DKS JellyLogin SSO plugin.
/// Edit via Jellyfin Admin → Dashboard → Plugins → DKS JellyLogin SSO.
/// </summary>
public class PluginConfiguration : BasePluginConfiguration
{
    /// <summary>Whether this auth provider is active.</summary>
    public bool Enabled { get; set; } = true;

    /// <summary>Full base URL of the DKS JellyLogin instance, e.g. http://192.168.1.10:5000</summary>
    public string ServerUrl { get; set; } = "http://localhost:5000";

    /// <summary>
    /// Shared secret copied from JellyLogin Admin → Einstellungen → Plugin-Secret.
    /// Used to authenticate plugin requests on the JellyLogin side.
    /// </summary>
    public string PluginSecret { get; set; } = string.Empty;

    /// <summary>
    /// When true, a new Jellyfin user account is automatically created on the first
    /// successful JellyLogin authentication if no matching user exists in Jellyfin.
    /// </summary>
    public bool CreateUsersOnFirstLogin { get; set; } = true;
}
