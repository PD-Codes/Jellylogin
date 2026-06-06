using System;
using System.Net;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json.Serialization;
using System.Threading.Tasks;
using Jellyfin.Data.Entities;
using MediaBrowser.Controller.Authentication;
using Microsoft.Extensions.Logging;

namespace JellyLogin.Plugin;

/// <summary>
/// Jellyfin authentication provider that delegates credential validation
/// to a running DKS JellyLogin instance via its /api/plugin/auth endpoint.
/// </summary>
public sealed class JellyLoginAuthProvider : IAuthenticationProvider
{
    private readonly ILogger<JellyLoginAuthProvider> _logger;

    // Shared across all requests; thread-safe and efficient.
    private static readonly HttpClient _http = new(new SocketsHttpHandler
    {
        PooledConnectionLifetime = TimeSpan.FromMinutes(5),
        ConnectTimeout = TimeSpan.FromSeconds(8),
    })
    {
        Timeout = TimeSpan.FromSeconds(12),
    };

    public string Name => "DKS JellyLogin";

    public bool IsEnabled => Plugin.Instance?.Configuration.Enabled ?? false;

    public JellyLoginAuthProvider(ILogger<JellyLoginAuthProvider> logger)
    {
        _logger = logger;
    }

    /// <inheritdoc />
    public bool HasPassword(User user) => true;

    /// <inheritdoc />
    public Task ChangePassword(User user, string newPassword) =>
        throw new NotImplementedException(
            "Passwörter werden in DKS JellyLogin verwaltet. " +
            "Bitte melde dich dort an und ändere dein Passwort.");

    /// <inheritdoc />
    public async Task<ProviderAuthenticationResult> Authenticate(string username, string password)
    {
        var config = Plugin.Instance?.Configuration
            ?? throw new AuthenticationException("Plugin-Konfiguration nicht verfügbar.");

        if (!config.Enabled)
            throw new AuthenticationException("DKS JellyLogin SSO ist deaktiviert.");

        if (string.IsNullOrWhiteSpace(config.ServerUrl))
            throw new AuthenticationException("DKS JellyLogin Server-URL ist nicht konfiguriert.");

        if (string.IsNullOrWhiteSpace(config.PluginSecret))
            throw new AuthenticationException("Plugin-Secret ist nicht konfiguriert. Bitte im Plugin-Admin eintragen.");

        var endpoint = $"{config.ServerUrl.TrimEnd('/')}/api/plugin/auth";

        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Post, endpoint);
            request.Headers.Add("X-Plugin-Secret", config.PluginSecret);
            request.Content = JsonContent.Create(new AuthRequest(username, password));

            _logger.LogDebug("DKS JellyLogin: Authentifizierung für {Username} → {Endpoint}", username, endpoint);

            using var response = await _http.SendAsync(request).ConfigureAwait(false);

            if (response.StatusCode == HttpStatusCode.Unauthorized)
            {
                _logger.LogInformation("DKS JellyLogin: Ungültige Anmeldedaten für {Username}", username);
                throw new AuthenticationException("Ungültige Anmeldedaten.");
            }

            if (response.StatusCode == HttpStatusCode.Forbidden)
                throw new AuthenticationException("DKS JellyLogin: Plugin-Secret ungültig. Konfiguration prüfen.");

            response.EnsureSuccessStatusCode();

            var result = await response.Content.ReadFromJsonAsync<AuthResponse>().ConfigureAwait(false);

            if (result?.Authenticated != true)
                throw new AuthenticationException("Authentifizierung fehlgeschlagen.");

            _logger.LogInformation("DKS JellyLogin: {Username} erfolgreich authentifiziert (Rolle: {Role})",
                result.Username, result.Role);

            return new ProviderAuthenticationResult { Username = result.Username };
        }
        catch (AuthenticationException)
        {
            throw;
        }
        catch (HttpRequestException ex)
        {
            _logger.LogError(ex, "DKS JellyLogin: Verbindungsfehler zu {Endpoint}", endpoint);
            throw new AuthenticationException(
                $"DKS JellyLogin Server nicht erreichbar ({endpoint}). " +
                $"Stelle sicher, dass JellyLogin läuft. Fehler: {ex.Message}");
        }
        catch (TaskCanceledException ex) when (ex.InnerException is TimeoutException)
        {
            _logger.LogError("DKS JellyLogin: Timeout bei Verbindung zu {Endpoint}", endpoint);
            throw new AuthenticationException($"DKS JellyLogin: Verbindungstimeout zu {endpoint}.");
        }
        catch (Exception ex) when (ex is not AuthenticationException)
        {
            _logger.LogError(ex, "DKS JellyLogin: Unerwarteter Fehler für {Username}", username);
            throw new AuthenticationException($"Unerwarteter Fehler: {ex.Message}");
        }
    }

    // ── DTOs ─────────────────────────────────────────────────────────────────

    private sealed record AuthRequest(
        [property: JsonPropertyName("username")] string Username,
        [property: JsonPropertyName("password")] string Password);

    private sealed class AuthResponse
    {
        [JsonPropertyName("authenticated")]
        public bool Authenticated { get; init; }

        [JsonPropertyName("username")]
        public string Username { get; init; } = string.Empty;

        [JsonPropertyName("role")]
        public string Role { get; init; } = string.Empty;
    }
}
