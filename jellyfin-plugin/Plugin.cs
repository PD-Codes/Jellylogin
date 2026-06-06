using System;
using System.Collections.Generic;
using MediaBrowser.Common.Configuration;
using MediaBrowser.Common.Plugins;
using MediaBrowser.Model.Plugins;
using MediaBrowser.Model.Serialization;

namespace JellyLogin.Plugin;

/// <summary>
/// DKS JellyLogin SSO plugin for Jellyfin.
/// Authenticates users against a running DKS JellyLogin instance.
/// </summary>
public sealed class Plugin : BasePlugin<PluginConfiguration>, IHasWebPages
{
    /// <summary>Singleton instance set during construction.</summary>
    public static Plugin? Instance { get; private set; }

    public override string Name => "DKS JellyLogin SSO";

    // Keep this GUID stable — changing it resets all saved configuration.
    public override Guid Id => new Guid("c3a7f210-4d8e-4b5a-9f62-1a2b3c4d5e6f");

    public override string Description =>
        "Single Sign-On via DKS JellyLogin. " +
        "Allows Jellyfin users to authenticate with their DKS JellyLogin credentials.";

    public Plugin(IApplicationPaths applicationPaths, IXmlSerializer xmlSerializer)
        : base(applicationPaths, xmlSerializer)
    {
        Instance = this;
    }

    /// <inheritdoc />
    public IEnumerable<PluginPageInfo> GetPages()
    {
        yield return new PluginPageInfo
        {
            Name = Name,
            EmbeddedResourcePath = $"{GetType().Namespace}.Configuration.configPage.html"
        };
    }
}
