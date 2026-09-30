using System.Diagnostics;

namespace Legacy.Maliev.ProcurementService.Tests.Startup;

public sealed class DockerContextPrivacyTests
{
    [Fact]
    public async Task ActualDockerContext_ExcludesNestedPrivateArtifactsAndKeepsRequiredDependencySources()
    {
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null && !File.Exists(Path.Combine(root.FullName, "Legacy.Maliev.ProcurementService.slnx"))) root = root.Parent;
        Assert.NotNull(root);
        var fixture = Path.Combine(Path.GetTempPath(), "procurement-context-acceptance-" + Guid.NewGuid().ToString("N"));
        var image = "procurement-context-acceptance:" + Guid.NewGuid().ToString("N");
        Directory.CreateDirectory(fixture);
        try
        {
            File.Copy(Path.Combine(root.FullName, ".dockerignore"), Path.Combine(fixture, ".dockerignore"));
            string[] excluded = [".env.production", "nested/.git/config", ".dependencies/Library/.git/config",
                "nested/private.env", "nested/.env.local", "nested/private.pem", "nested/private.key",
                "nested/private.pfx", "nested/debug.log", "nested/scratch.tmp", "nested/TestResults/result.xml",
                "nested/coverage/result.xml", "nested/bin/generated.xml", "nested/obj/generated.xml",
                "nested/deployment.yaml", "nested/deploy.ps1", "nested/deploy.sh", "nested/node_modules/private.js",
                "nested/dist/generated.js", "nested/source.swp", "nested/source.swo", "nested/.gitignore", "nested/Dockerfile.dockerignore"];
            string[] retained = ["Api/Program.cs", "Api/Api.csproj", ".dependencies/Library/src/Library.csproj",
                ".dependencies/Library/src/Extensions.cs", ".dependencies/Library/Directory.Build.props", "nuget.config"];
            foreach (var relative in excluded.Concat(retained))
            {
                var path = Path.Combine(fixture, relative.Replace('/', Path.DirectorySeparatorChar));
                Directory.CreateDirectory(Path.GetDirectoryName(path)!);
                await File.WriteAllTextAsync(path, "acceptance-canary-not-a-secret");
            }
            var checks = retained.Select(path => $"test -f /context/{path}")
                .Concat(excluded.Select(path => $"test ! -e /context/{path}"));
            await File.WriteAllTextAsync(Path.Combine(fixture, "Dockerfile"),
                "FROM busybox:1.37\nCOPY . /context/\nRUN " + string.Join(" && ", checks) + "\n");
            var result = await DockerAsync("build", "--quiet", "--tag", image, fixture);
            Assert.True(result.ExitCode == 0, "Actual Docker context contains private artifacts or excludes required source:\n" + result.Output);
        }
        finally
        {
            await DockerAsync("image", "rm", "--force", image);
            // Unique fixture created above; never a repository or user-owned directory.
            Directory.Delete(fixture, recursive: true);
        }
    }

    private static async Task<(int ExitCode, string Output)> DockerAsync(params string[] arguments)
    {
        var start = new ProcessStartInfo("docker") { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
        foreach (var argument in arguments) start.ArgumentList.Add(argument);
        using var process = Process.Start(start) ?? throw new InvalidOperationException("Docker could not start.");
        var output = process.StandardOutput.ReadToEndAsync();
        var error = process.StandardError.ReadToEndAsync();
        using var timeout = new CancellationTokenSource(TimeSpan.FromMinutes(3));
        try { await process.WaitForExitAsync(timeout.Token); }
        catch (OperationCanceledException) { process.Kill(entireProcessTree: true); throw; }
        return (process.ExitCode, await output + await error);
    }
}
