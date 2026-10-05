using System.Text.RegularExpressions;

using YamlDotNet.Core;
using YamlDotNet.RepresentationModel;

namespace Legacy.Maliev.ProcurementService.Tests.Workflows;

public sealed class WorkflowContractTests
{
    private const string ReviewedProducerVersion = "b27fbef06a3aa58c1f4fc0e75d7c70b32be76266";
    private static readonly string Workflow = File.ReadAllText(FindRepositoryFile(".github", "workflows", "_build-and-test.yml"));
    private static readonly string ApiProject = File.ReadAllText(
        FindRepositoryFile("Legacy.Maliev.ProcurementService.Api", "Legacy.Maliev.ProcurementService.Api.csproj"));
    private static readonly string DataProject = File.ReadAllText(
        FindRepositoryFile("Legacy.Maliev.ProcurementService.Data", "Legacy.Maliev.ProcurementService.Data.csproj"));

    [Fact]
    public void BuildAndTest_SatisfiesStructuralContract()
    {
        WorkflowContractValidator.Validate(Workflow);
    }

    [Fact]
    public void DependabotConfiguration_ScansOnlyIndependentlyResolvableProjectDirectories()
    {
        var source = File.ReadAllText(FindRepositoryFile(".github", "dependabot.yml"));
        var yaml = new YamlStream();
        yaml.Load(new StringReader(source));

        var root = Assert.IsType<YamlMappingNode>(Assert.Single(yaml.Documents).RootNode);
        var updates = Assert.IsType<YamlSequenceNode>(ReadNode(root, "updates"));
        var nuget = updates.Children
            .Select(Assert.IsType<YamlMappingNode>)
            .Single(update => ReadScalar(update, "package-ecosystem") == "nuget");
        var directories = Assert.IsType<YamlSequenceNode>(ReadNode(nuget, "directories"));

        Assert.Equal(
            [
                "/Legacy.Maliev.ProcurementService.Application",
                "/Legacy.Maliev.ProcurementService.Data",
                "/Legacy.Maliev.ProcurementService.Domain",
            ],
            directories.Children.Select(Assert.IsType<YamlScalarNode>).Select(node => node.Value));
        Assert.False(nuget.Children.ContainsKey(new YamlScalarNode("directory")));
        Assert.False(nuget.Children.ContainsKey(new YamlScalarNode("exclude-paths")));
    }

    [Fact]
    public void DependabotConfiguration_AllowsCoordinatedEfUpdatesAndDefersSharedRuntimePackages()
    {
        var source = File.ReadAllText(FindRepositoryFile(".github", "dependabot.yml"));
        var yaml = new YamlStream();
        yaml.Load(new StringReader(source));

        var root = Assert.IsType<YamlMappingNode>(Assert.Single(yaml.Documents).RootNode);
        var updates = Assert.IsType<YamlSequenceNode>(ReadNode(root, "updates"));
        var nuget = updates.Children
            .Select(Assert.IsType<YamlMappingNode>)
            .Single(update => ReadScalar(update, "package-ecosystem") == "nuget");
        var ignored = Assert.IsType<YamlSequenceNode>(ReadNode(nuget, "ignore"));
        var rules = ignored.Children.Select(Assert.IsType<YamlMappingNode>).ToArray();

        Assert.Equal(
            [
                "Legacy.Maliev.ServiceDefaults",
                "Legacy.Maliev.CompatibilityContracts",
            ],
            rules.Select(rule => ReadScalar(rule, "dependency-name")));
    }

    [Fact]
    public void BuildAndTest_RejectsSharedActionMainWithPinnedShaComment()
    {
        AssertMutationRejected(
            "MALIEV-Co-Ltd/Legacy.Maliev.Workflows/actions/dotnet-validate@e3a6093324a24968876782153286f52db8b29fd8",
            "MALIEV-Co-Ltd/Legacy.Maliev.Workflows/actions/dotnet-validate@main # e3a6093324a24968876782153286f52db8b29fd8");
    }

    [Fact]
    public void BuildAndTest_RejectsCommentedDependencySha()
    {
        AssertMutationRejected(
            "ref: ecb05cbbd68717e415f69df2ac488c1d323b1da3",
            "ref: main # ecb05cbbd68717e415f69df2ac488c1d323b1da3");
    }

    [Fact]
    public void BuildAndTest_RejectsMissingOwnedCoverageGate()
    {
        AssertMutationRejected(
            "      - name: Gate owned production coverage\n        run: python3 scripts/verify-runner-coverage.py runner-results\n",
            string.Empty);
    }

    [Fact]
    public void BuildAndTest_RejectsEvidenceThatDoesNotSurviveFailure()
    {
        AssertMutationRejected("        if: always()", "        if: success()");
    }

    [Fact]
    public void ApiProject_UsesOnlyLegacyServiceDefaults()
    {
        Assert.Contains("Legacy.Maliev.ServiceDefaults", ApiProject, StringComparison.Ordinal);
        Assert.DoesNotContain("Maliev.Aspire\\Maliev.Aspire.ServiceDefaults", ApiProject, StringComparison.Ordinal);
        Assert.DoesNotContain("Include=\"Maliev.Aspire.ServiceDefaults\"", ApiProject, StringComparison.Ordinal);
    }

    [Fact]
    public void EfDesignDependency_IsOwnedByDataProjectOnly()
    {
        Assert.DoesNotContain("Microsoft.EntityFrameworkCore.Design", ApiProject, StringComparison.Ordinal);
        Assert.Contains("Microsoft.EntityFrameworkCore.Design", DataProject, StringComparison.Ordinal);
    }

    [Fact]
    public void BuildAndTest_RejectsJobPermissionEscalation()
    {
        AssertMutationRejected(
            "  validate:\n    name: validate",
            "  validate:\n    permissions:\n      contents: write\n    name: validate");
    }

    [Fact]
    public void BuildAndTest_RejectsSecretReferenceAnywhere()
    {
        var mutated = $"{Workflow}\n# ${{{{ secrets.X }}}}\n";

        Assert.Throws<InvalidOperationException>(() => WorkflowContractValidator.Validate(mutated));
    }

    [Theory]
    [InlineData("${{secrets.X}}")]
    [InlineData("${{ secrets['X'] }}")]
    public void BuildAndTest_RejectsSecretExpressionInJobEnvironment(string expression)
    {
        AssertMutationRejected(
            "    env:\n      MalievWorkspaceRoot: ${{ github.workspace }}/.dependencies",
            $"    env:\n      MalievWorkspaceRoot: ${{{{ github.workspace }}}}/.dependencies\n      REVIEW_TOKEN: {expression}");
    }

    [Fact]
    public void BuildAndTest_RejectsWhitespaceObfuscatedRestoreCommand()
    {
        AssertMutationRejected(
            "          solution: Legacy.Maliev.ProcurementService.slnx",
            "          solution: Legacy.Maliev.ProcurementService.slnx\n      - run: dotnet  restore Legacy.Maliev.ProcurementService.slnx");
    }

    [Fact]
    public void BuildAndTest_RejectsMissingLocalDependencyOptIn()
    {
        AssertMutationRejected(
            "          use-local-maliev-dependencies: 'true'\n",
            string.Empty);
    }

    [Fact]
    public void BuildAndTest_RejectsReservedGitHubActionsOverride()
    {
        AssertMutationRejected(
            "          use-local-maliev-dependencies: 'true'\n",
            "          use-local-maliev-dependencies: 'true'\n        env:\n          GITHUB_ACTIONS: 'false'\n");
    }

    [Fact]
    public void ActualAuthProgramJoin_RequiresImmutableProducersAndAlwaysRetainedEvidence()
    {
        ValidateAuthProgramJoin(File.ReadAllText(FindRepositoryFile(".github", "workflows", "procurement-auth-program-validation.yml")));
    }

    [Theory]
    [InlineData("b27fbef06a3aa58c1f4fc0e75d7c70b32be76266", "main")]
    [InlineData("ecb05cbbd68717e415f69df2ac488c1d323b1da3", "7edcd961024868513fd5f373cab3dcb261197f77")]
    [InlineData("if: always()", "if: failure()")]
    [InlineData("python3 -B scripts/verify-procurement-auth-program.py results auth-program-results", "python3 -c 'print(0)'")]
    public void ActualAuthProgramJoin_RejectsMutableProducerOrMissingAcceptanceGate(string original, string replacement)
    {
        var source = File.ReadAllText(FindRepositoryFile(".github", "workflows", "procurement-auth-program-validation.yml"));
        Assert.Contains(original, source, StringComparison.Ordinal);
        Assert.Throws<InvalidOperationException>(() => ValidateAuthProgramJoin(source.Replace(original, replacement, StringComparison.Ordinal)));
    }

    private static void ValidateAuthProgramJoin(string source)
    {
        var yaml = new YamlStream();
        yaml.Load(new StringReader(source));
        var root = (YamlMappingNode)yaml.Documents.Single().RootNode;
        var job = (YamlMappingNode)ReadNode((YamlMappingNode)ReadNode(root, "jobs"), "auth-program");
        var steps = ((YamlSequenceNode)ReadNode(job, "steps")).Children.Cast<YamlMappingNode>().ToArray();
        var expected = new (string Repository, string Commit)[]
        {
            ("MALIEV-Co-Ltd/Legacy.Maliev.AuthService", ReviewedProducerVersion),
            ("MALIEV-Co-Ltd/Legacy.Maliev.ServiceDefaults", "ecb05cbbd68717e415f69df2ac488c1d323b1da3"),
            ("MALIEV-Co-Ltd/Legacy.Maliev.CompatibilityContracts", "78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7"),
            ("MALIEV-Co-Ltd/Legacy.Maliev.ProcurementService", "da6af357254f1e42d95ce592bc716b2ae0abb4cf"),
        }.ToDictionary(entry => entry.Repository, entry => entry.Commit);
        var checkouts = steps.Where(step => step.Children.TryGetValue(new YamlScalarNode("with"), out var node)
            && node is YamlMappingNode settings && settings.Children.ContainsKey(new YamlScalarNode("repository"))).ToArray();
        if (checkouts.Length != expected.Count) throw new InvalidOperationException("Require exactly the four reviewed producer checkouts.");
        foreach (var checkout in checkouts)
        {
            var settings = (YamlMappingNode)ReadNode(checkout, "with");
            if (!expected.TryGetValue(ReadScalar(settings, "repository"), out var pin) || ReadScalar(settings, "ref") != pin
                || ReadScalar(settings, "persist-credentials") != "false")
                throw new InvalidOperationException("Producer checkout must retain its reviewed hard pin without credentials.");
        }
        var results = steps.Single(step => step.Children.TryGetValue(new YamlScalarNode("run"), out var run)
            && ((YamlScalarNode)run).Value == "python3 -B scripts/verify-procurement-auth-program.py results auth-program-results");
        var artifact = steps.Single(step => step.Children.TryGetValue(new YamlScalarNode("uses"), out var uses)
            && ((YamlScalarNode)uses).Value == "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        if (ReadScalar(results, "if") != "always()" || ReadScalar(artifact, "if") != "always()"
            || ReadScalar((YamlMappingNode)ReadNode(artifact, "with"), "path") != "auth-program-results")
            throw new InvalidOperationException("Joined executions and failure evidence must always be checked/retained.");
    }

    private static void AssertMutationRejected(string original, string replacement)
    {
        Assert.Contains(original, Workflow, StringComparison.Ordinal);
        var mutated = Workflow.Replace(original, replacement, StringComparison.Ordinal);

        Assert.Throws<InvalidOperationException>(() => WorkflowContractValidator.Validate(mutated));
    }

    private static YamlNode ReadNode(YamlMappingNode mapping, string key)
    {
        return mapping.Children[new YamlScalarNode(key)];
    }

    private static string ReadScalar(YamlMappingNode mapping, string key)
    {
        return Assert.IsType<YamlScalarNode>(ReadNode(mapping, key)).Value
            ?? throw new InvalidOperationException($"Expected '{key}' to have a scalar value.");
    }

    private static string FindRepositoryFile(params string[] segments)
    {
        DirectoryInfo? directory = new(AppContext.BaseDirectory);

        while (directory is not null)
        {
            var candidate = Path.Combine([directory.FullName, .. segments]);
            if (File.Exists(candidate))
            {
                return candidate;
            }

            directory = directory.Parent;
        }

        throw new FileNotFoundException($"Could not find repository file '{Path.Combine(segments)}'.");
    }
}

internal static partial class WorkflowContractValidator
{
    private const string CheckoutAction = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1";
    private const string SharedValidationAction = "MALIEV-Co-Ltd/Legacy.Maliev.Workflows/actions/dotnet-validate@e3a6093324a24968876782153286f52db8b29fd8";

    public static void Validate(string workflow)
    {
        if (SecretExpression().IsMatch(workflow))
        {
            throw new InvalidOperationException("Workflow must not reference secrets.");
        }

        var yaml = new YamlStream();
        try
        {
            yaml.Load(new StringReader(workflow));
        }
        catch (Exception exception)
        {
            throw new InvalidOperationException("Workflow must be valid YAML.", exception);
        }

        if (yaml.Documents.Count != 1 || yaml.Documents[0].RootNode is not YamlMappingNode root)
        {
            throw new InvalidOperationException("Workflow must contain exactly one mapping document.");
        }

        var workflowPermissions = RequireExactReadOnlyPermissions(RequireMapping(root, "permissions"), "workflow");
        var jobs = RequireMapping(root, "jobs");
        if (jobs.Children.Count != 1)
        {
            throw new InvalidOperationException("Workflow must define only the validate job.");
        }

        var validateJob = RequireMapping(jobs, "validate");
        var jobPermissionsNode = GetOptional(validateJob, "permissions");
        var effectiveJobPermissions = jobPermissionsNode is null
            ? workflowPermissions
            : RequireExactReadOnlyPermissions(RequireMapping(jobPermissionsNode, "jobs.validate.permissions"), "validate job");
        if (!effectiveJobPermissions.SequenceEqual(workflowPermissions, StringComparer.Ordinal))
        {
            throw new InvalidOperationException("Validate job permissions must not differ from workflow permissions.");
        }

        RequireScalarValue(validateJob, "name", "validate");
        RejectDuplicatedValidationActionsAndCommands(jobs);

        var steps = RequireSequence(validateJob, "steps");
        if (steps.Children.Count != 6)
        {
            throw new InvalidOperationException("Validate job must contain four validation and two evidence steps.");
        }

        var environment = RequireMapping(validateJob, "env");
        if (environment.Children.Count != 4)
        {
            throw new InvalidOperationException("Validate environment must contain only dependency root and evidence properties.");
        }

        RequireScalarValue(environment, "MalievWorkspaceRoot", "${{ github.workspace }}/.dependencies");
        RequireScalarValue(environment, "VSTestCollect", "XPlat Code Coverage");
        RequireScalarValue(environment, "VSTestLogger", "trx");
        RequireScalarValue(environment, "VSTestResultsDirectory", "${{ github.workspace }}/runner-results");

        var gate = RequireMapping(steps.Children[4], "coverage gate");
        if (gate.Children.Count != 2)
        {
            throw new InvalidOperationException("Coverage gate must contain only name and run.");
        }

        RequireScalarValue(gate, "name", "Gate owned production coverage");
        RequireScalarValue(gate, "run", "python3 scripts/verify-runner-coverage.py runner-results");
        var evidence = RequireMapping(steps.Children[5], "evidence upload");
        if (evidence.Children.Count != 4)
        {
            throw new InvalidOperationException("Evidence upload must contain exactly name, if, uses and with.");
        }

        RequireScalarValue(evidence, "name", "Preserve validation evidence");
        RequireScalarValue(evidence, "if", "always()");
        RequireScalarValue(evidence, "uses", "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02");
        var evidenceInputs = RequireMapping(evidence, "with");
        if (evidenceInputs.Children.Count != 4)
        {
            throw new InvalidOperationException("Evidence upload must have exactly four bounded inputs.");
        }

        RequireScalarValue(evidenceInputs, "name", "procurement-validation-${{ github.sha }}");
        RequireScalarValue(evidenceInputs, "path", "runner-results");
        RequireScalarValue(evidenceInputs, "if-no-files-found", "warn");
        RequireScalarValue(evidenceInputs, "retention-days", "7");

        ValidateStep(
            steps.Children[0],
            CheckoutAction,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["persist-credentials"] = "false",
            });
        ValidateStep(
            steps.Children[1],
            CheckoutAction,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["repository"] = "MALIEV-Co-Ltd/Legacy.Maliev.ServiceDefaults",
                ["ref"] = "ecb05cbbd68717e415f69df2ac488c1d323b1da3",
                ["path"] = ".dependencies/Legacy.Maliev.ServiceDefaults",
                ["persist-credentials"] = "false",
            });
        ValidateStep(
            steps.Children[2],
            CheckoutAction,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["repository"] = "MALIEV-Co-Ltd/Legacy.Maliev.CompatibilityContracts",
                ["ref"] = "78e48ffc4ee000df0510cba5e7c7a3c4c4d539d7",
                ["path"] = ".dependencies/Legacy.Maliev.CompatibilityContracts",
                ["persist-credentials"] = "false",
            });
        ValidateStep(
            steps.Children[3],
            SharedValidationAction,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["solution"] = "Legacy.Maliev.ProcurementService.slnx",
                ["use-local-maliev-dependencies"] = "true",
            });
    }

    private static IReadOnlyList<string> RequireExactReadOnlyPermissions(YamlMappingNode permissions, string scope)
    {
        if (permissions.Children.Count != 1)
        {
            throw new InvalidOperationException($"{scope} permissions must contain only contents: read.");
        }

        RequireScalarValue(permissions, "contents", "read");
        return ["contents:read"];
    }

    private static void ValidateStep(
        YamlNode node,
        string expectedAction,
        IReadOnlyDictionary<string, string> expectedInputs)
    {
        var step = RequireMapping(node, "workflow step");
        var allowedKeys = new HashSet<string>(["name", "uses", "with"], StringComparer.Ordinal);

        var actualKeys = step.Children.Keys.Select(RequireScalar).ToHashSet(StringComparer.Ordinal);
        if (!actualKeys.SetEquals(allowedKeys))
        {
            throw new InvalidOperationException("Each workflow step must contain exactly name, uses, and with.");
        }

        var name = RequireScalar(GetRequired(step, "name"));
        if (string.IsNullOrWhiteSpace(name))
        {
            throw new InvalidOperationException("Workflow step name must not be empty.");
        }

        RequireScalarValue(step, "uses", expectedAction);
        var inputs = RequireMapping(step, "with");
        if (inputs.Children.Count != expectedInputs.Count)
        {
            throw new InvalidOperationException($"Action {expectedAction} has an unexpected input count.");
        }

        foreach (var expectedInput in expectedInputs)
        {
            RequireScalarValue(inputs, expectedInput.Key, expectedInput.Value);
        }

        var environment = GetOptional(step, "env");
        if (environment is not null)
        {
            throw new InvalidOperationException("Workflow action steps must not override reserved environment variables.");
        }

        if (expectedInputs.ContainsKey("use-local-maliev-dependencies"))
        {
            var useLocalDependencies = GetRequired(inputs, "use-local-maliev-dependencies") as YamlScalarNode;
            if (useLocalDependencies?.Style != ScalarStyle.SingleQuoted)
            {
                throw new InvalidOperationException("use-local-maliev-dependencies must use the single-quoted string value 'true'.");
            }
        }
    }

    private static void RejectDuplicatedValidationActionsAndCommands(YamlMappingNode jobs)
    {
        foreach (var jobNode in jobs.Children.Values.OfType<YamlMappingNode>())
        {
            var stepsNode = GetOptional(jobNode, "steps");
            if (stepsNode is not YamlSequenceNode steps)
            {
                continue;
            }

            foreach (var stepNode in steps.Children.OfType<YamlMappingNode>())
            {
                if (GetOptional(stepNode, "uses") is YamlScalarNode usesNode)
                {
                    var action = usesNode.Value ?? string.Empty;
                    if (action.StartsWith("actions/setup-dotnet@", StringComparison.OrdinalIgnoreCase)
                        || action.StartsWith("actions/cache@", StringComparison.OrdinalIgnoreCase))
                    {
                        throw new InvalidOperationException($"Caller duplicates shared action {action}.");
                    }
                }

                if (GetOptional(stepNode, "run") is YamlScalarNode runNode)
                {
                    RejectDuplicatedDotNetCommand(runNode.Value ?? string.Empty);
                }
            }
        }
    }

    private static void RejectDuplicatedDotNetCommand(string command)
    {
        var tokens = command
            .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Select(token => token.Trim('"', '\'', ';', '&', '|').ToLowerInvariant())
            .Where(token => token.Length > 0)
            .ToArray();

        for (var index = 0; index < tokens.Length - 1; index++)
        {
            if (!string.Equals(tokens[index], "dotnet", StringComparison.Ordinal))
            {
                continue;
            }

            var verb = tokens[index + 1];
            if (verb is "restore" or "build" or "test" or "format" or "list"
                || tokens[(index + 1)..].Any(token => token is "audit" or "--vulnerable"))
            {
                throw new InvalidOperationException($"Caller duplicates shared dotnet validation command: {verb}.");
            }
        }
    }

    private static YamlMappingNode RequireMapping(YamlMappingNode parent, string key) =>
        RequireMapping(GetRequired(parent, key), key);

    private static YamlMappingNode RequireMapping(YamlNode node, string description)
    {
        return node as YamlMappingNode
            ?? throw new InvalidOperationException($"{description} must be a mapping.");
    }

    private static YamlSequenceNode RequireSequence(YamlMappingNode parent, string key)
    {
        return GetRequired(parent, key) as YamlSequenceNode
            ?? throw new InvalidOperationException($"{key} must be a sequence.");
    }

    private static void RequireScalarValue(YamlMappingNode parent, string key, string expected)
    {
        var actual = RequireScalar(GetRequired(parent, key));
        if (!string.Equals(actual, expected, StringComparison.Ordinal))
        {
            throw new InvalidOperationException($"{key} must equal '{expected}', but was '{actual}'.");
        }
    }

    private static string RequireScalar(YamlNode node)
    {
        return (node as YamlScalarNode)?.Value
            ?? throw new InvalidOperationException("Expected a scalar YAML value.");
    }

    private static YamlNode GetRequired(YamlMappingNode parent, string key)
    {
        return GetOptional(parent, key)
            ?? throw new InvalidOperationException($"Missing required YAML key '{key}'.");
    }

    private static YamlNode? GetOptional(YamlMappingNode parent, string key)
    {
        foreach (var child in parent.Children)
        {
            if (child.Key is YamlScalarNode scalar && string.Equals(scalar.Value, key, StringComparison.Ordinal))
            {
                return child.Value;
            }
        }

        return null;
    }

    [GeneratedRegex(@"\$\{\{\s*secrets\s*(?:\.|\[)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant)]
    private static partial Regex SecretExpression();
}
