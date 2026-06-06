using MediaBrowser.Controller;
using MediaBrowser.Controller.Authentication;
using MediaBrowser.Controller.Plugins;
using Microsoft.Extensions.DependencyInjection;

namespace JellyLogin.Plugin;

/// <summary>
/// Registers plugin services into Jellyfin's dependency-injection container.
/// Jellyfin discovers this class automatically via the assembly attribute.
/// </summary>
public sealed class PluginServiceRegistrator : IPluginServiceRegistrator
{
    /// <inheritdoc />
    public void RegisterServices(IServiceCollection serviceCollection, IServerApplicationHost applicationHost)
    {
        serviceCollection.AddSingleton<IAuthenticationProvider, JellyLoginAuthProvider>();
    }
}
