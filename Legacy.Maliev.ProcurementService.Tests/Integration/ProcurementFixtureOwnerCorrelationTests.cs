using System.Reflection;
using System.Text.Json;

namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class ProcurementFixtureOwnerCorrelationTests
{
    private const string Prefix = "Legacy.Maliev.ProcurementService.Tests.Integration.";
    private static ProcurementFixtureOwnerCorrelation Correlation(Func<int, string, CancellationToken, Task>? publish = null)
        => new(ProcurementFixtureConsumer.SupplierTransaction, Prefix + "SupplierTransactionOwnedFixture", Guid.NewGuid().ToString("N"), publish);

    [Fact]
    public void WrapperConstructors_ValidateActualIdentityBeforeRsaAndContainerAllocation()
    {
        object[] wrappers = [new SupplierTransactionOwnedFixture(), new ChildLifecycleOwnedFixture(), new OpenApiContractOwnedFixture()];
        foreach (var wrapper in wrappers)
        {
            foreach (var field in new[] { "supplier", "order", "signingKey" })
                Assert.Null(typeof(ProcurementRuntimeFixture).GetField(field, BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(wrapper));
            var owner = (ProcurementFixtureOwnerCorrelation)typeof(ProcurementRuntimeFixture).GetField("ownerCorrelation", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(wrapper)!;
            Assert.Equal(wrapper.GetType().FullName, owner.Identity.FixtureType);
            Assert.NotNull(owner.Identity.ConsumerClass);
        }
    }

    [Fact]
    public void UnknownOrMismatchedDescriptor_FailsBeforePublicationOrResourceAction()
    {
        var called = false;
        Task Publish(int _, string __, CancellationToken ___) { called = true; return Task.CompletedTask; }
        Assert.Throws<ArgumentOutOfRangeException>(() => new ProcurementFixtureOwnerCorrelation((ProcurementFixtureConsumer)999, Prefix + "SupplierTransactionOwnedFixture", Guid.NewGuid().ToString("N"), Publish));
        Assert.Throws<InvalidOperationException>(() => new ProcurementFixtureOwnerCorrelation(ProcurementFixtureConsumer.ChildLifecycle, Prefix + "SupplierTransactionOwnedFixture", Guid.NewGuid().ToString("N"), Publish));
        Assert.False(called);
    }

    [Fact]
    public void UnattributedDescriptor_CannotNameAnOwnedWrapper()
    {
        Assert.Throws<InvalidOperationException>(() => new ProcurementFixtureOwnerCorrelation(ProcurementFixtureConsumer.UnattributedRuntime, Prefix + "SupplierTransactionOwnedFixture", Guid.NewGuid().ToString("N")));
        var owner = new ProcurementFixtureOwnerCorrelation(ProcurementFixtureConsumer.UnattributedRuntime, Prefix + "ProcurementRuntimeFixture", Guid.NewGuid().ToString("N"));
        Assert.Null(owner.Identity.ConsumerClass);
    }

    [Fact]
    public void SeparateFixtureInstances_HaveDistinctIdentityWithoutNativeExecutionClaim()
    {
        var first = Correlation(); var second = Correlation();
        Assert.NotEqual(first.Identity.FixtureInstanceId, second.Identity.FixtureInstanceId);
        Assert.NotEqual(first.Identity.ResourceRunId, second.Identity.ResourceRunId);
        Assert.False(first.Identity.DirectNativeExecutionJoin);
        using var receipt = JsonDocument.Parse(first.Serialize(0, "setup"));
        Assert.Equal(JsonValueKind.Null, receipt.RootElement.GetProperty("NativeExecutionId").ValueKind);
        Assert.False(receipt.RootElement.GetProperty("TerminalCleanupProven").GetBoolean());
    }

    [Fact]
    public void CleanupInvocations_AreDistinctAndClockEventsMonotonic()
    {
        var owner = Correlation();
        Assert.Equal(1, owner.BeginCleanup()); Assert.Equal(2, owner.BeginCleanup());
        using var receipt = JsonDocument.Parse(owner.Serialize(2, "after-cleanup"));
        var events = receipt.RootElement.GetProperty("Events").EnumerateArray().ToArray();
        Assert.Equal(new[] { 1, 2, 3 }, events.Select(item => item.GetProperty("Sequence").GetInt32()).ToArray());
        Assert.True(events.Zip(events.Skip(1)).All(pair => pair.First.GetProperty("ElapsedTicks").GetInt64() <= pair.Second.GetProperty("ElapsedTicks").GetInt64()));
    }

    [Fact]
    public async Task OriginalSynchronousCleanupThrow_IsNotReplacedOrSkipped()
    {
        var owner = Correlation(); var original = new IOException("synthetic private value");
        var actual = await Assert.ThrowsAsync<IOException>(() => owner.ObserveCleanupAsync(owner.BeginCleanup(), "supplier", () => throw original));
        Assert.Same(original, actual);
        Assert.DoesNotContain(original.Message, System.Text.Encoding.UTF8.GetString(owner.Serialize(1, "after-cleanup")), StringComparison.Ordinal);
    }

    [Fact]
    public async Task OriginalCanceledCleanupToken_IsPreserved()
    {
        var owner = Correlation(); using var token = new CancellationTokenSource(); token.Cancel();
        var actual = await Assert.ThrowsAnyAsync<OperationCanceledException>(() => owner.ObserveCleanupAsync(owner.BeginCleanup(), "supplier", () => Task.FromCanceled(token.Token)));
        Assert.Equal(token.Token, actual.CancellationToken);
    }

    [Fact]
    public async Task SharedPendingPublication_RetainsActualTaskAndLateOriginalFailure()
    {
        var pending = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously); var count = 0;
        var owner = Correlation((_, _, _) => { count++; return pending.Task; });
        var first = owner.PublishAsync(0, "setup", CancellationToken.None);
        var second = owner.PublishAsync(0, "setup", CancellationToken.None);
        Assert.Same(first, second); Assert.False(first.IsCompleted);
        var original = new IOException("synthetic publication failure"); pending.SetException(original);
        Assert.Same(original, await Assert.ThrowsAsync<IOException>(() => first));
        Assert.Same(first, owner.PublishAsync(0, "setup", CancellationToken.None)); Assert.Equal(1, count);
    }

    [Fact]
    public async Task ReceiptLimit_DoesNotSkipActualCleanupRelease()
    {
        var written = false; var owner = Correlation((_, _, _) => { written = true; return Task.CompletedTask; });
        for (var index = 0; index < ProcurementFixtureOwnerCorrelation.MaximumCleanupInvocations; index++) owner.BeginCleanup();
        var invocation = owner.BeginCleanup(); var original = Assert.Single(owner.OriginalObservationFailures); var released = false;
        await owner.ObserveCleanupAsync(invocation, "supplier", () => { released = true; return Task.CompletedTask; });
        Assert.True(released);
        var publication = owner.PublishAsync(invocation, "after-cleanup", CancellationToken.None);
        Assert.Same(original, await Assert.ThrowsAsync<InvalidOperationException>(() => publication));
        Assert.True(written);
        Assert.Same(publication, owner.PublishAsync(owner.BeginCleanup(), "after-cleanup", CancellationToken.None));
    }

    [Fact]
    public void EventOverflow_RemainsExplicitAndBounded()
    {
        var owner = Correlation();
        for (var index = 0; index < 100; index++) owner.Record(0, "initialize-invoked");
        using var receipt = JsonDocument.Parse(owner.Serialize(0, "setup"));
        Assert.True(receipt.RootElement.GetProperty("Overflow").GetBoolean());
        Assert.Equal(ProcurementFixtureOwnerCorrelation.MaximumEvents, receipt.RootElement.GetProperty("Events").GetArrayLength());
    }

    [Fact]
    public void InvalidRunAndReceiptPhase_AreRejected()
    {
        Assert.Throws<InvalidOperationException>(() => new ProcurementFixtureOwnerCorrelation(ProcurementFixtureConsumer.SupplierTransaction, Prefix + "SupplierTransactionOwnedFixture", "not-a-run"));
        Assert.Throws<InvalidOperationException>(() => Correlation().Serialize(0, "../unknown"));
    }
    [Fact]
    public void UnknownProviderRoleOrMismatchedId_DoesNotCreateAnOwnershipReceipt()
    {
        var owner = Correlation();
        var actual = new Docker.DotNet.Models.ContainerInspectResponse { ID = new string('a', 64) };
        Assert.Throws<InvalidOperationException>(() => owner.CaptureInspection("unknown-role", actual.ID, actual, null, false));
        Assert.Throws<InvalidOperationException>(() => owner.CaptureInspection("supplier", new string('b', 64), actual, null, false));
        using var receipt = JsonDocument.Parse(owner.Serialize(0, "setup"));
        Assert.Equal(0, receipt.RootElement.GetProperty("Resources").GetArrayLength());
    }

    [Fact]
    public void UnknownEventMetadata_IsAnErrorWithoutPublishingItsText()
    {
        var owner = Correlation(); owner.Record(0, "synthetic-private-metadata", "synthetic-private-role");
        var bytes = owner.Serialize(0, "setup");
        Assert.DoesNotContain("synthetic-private", System.Text.Encoding.UTF8.GetString(bytes), StringComparison.Ordinal);
        using var receipt = JsonDocument.Parse(bytes);
        Assert.Equal(1, receipt.RootElement.GetProperty("ObservationFailureTypes").GetArrayLength());
    }
    [Fact]
    public void DurableWrappers_ValidateBeforeAnyRsaOrProviderAllocation()
    {
        object[] wrappers = [new DurableCreateOwnedFixture(), new DurableChildCreateOwnedFixture()];
        foreach (var wrapper in wrappers)
        {
            foreach (var field in new[] { "supplier", "order", "signingKey" })
                Assert.Null(typeof(ProcurementDurableCreateFixture).GetField(field, BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(wrapper));
            var owner = (ProcurementFixtureOwnerCorrelation)typeof(ProcurementDurableCreateFixture).GetField("ownerCorrelation", BindingFlags.NonPublic | BindingFlags.Instance)!.GetValue(wrapper)!;
            Assert.Equal(wrapper.GetType().FullName, owner.Identity.FixtureType);
        }
    }

    [Fact]
    public async Task AggregateCleanupFailure_RetainsEveryOriginalReference()
    {
        var first = new IOException("first synthetic failure"); var second = new InvalidOperationException("second synthetic failure");
        var original = new AggregateException(first, second); var owner = Correlation();
        var actual = await Assert.ThrowsAsync<AggregateException>(() => owner.ObserveCleanupAsync(owner.BeginCleanup(), "supplier", () => Task.FromException(original)));
        Assert.Same(original, actual); Assert.Same(first, actual.InnerExceptions[0]); Assert.Same(second, actual.InnerExceptions[1]);
    }
    [Fact]
    public async Task PendingCleanup_DoesNotPublishASettledEventUntilActualTaskFinishes()
    {
        var owner = Correlation(); var pending = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var invocation = owner.BeginCleanup(); var release = owner.ObserveCleanupAsync(invocation, "supplier", () => pending.Task);
        Assert.False(release.IsCompleted);
        using (var snapshot = JsonDocument.Parse(owner.Serialize(invocation, "after-cleanup")))
            Assert.DoesNotContain(snapshot.RootElement.GetProperty("Events").EnumerateArray(), item => item.GetProperty("Phase").GetString() == "callback-settled");
        var original = new IOException("synthetic late cleanup failure"); pending.SetException(original);
        Assert.Same(original, await Assert.ThrowsAsync<IOException>(() => release));
    }
    [Fact]
    public void CorrelationOnlyRefusal_PreservesBothOriginalIdVolumeScopesAndProgress()
    {
        var ids = new List<string>(); var volumes = new List<string>(); var errors = new List<Exception>();
        var refused = new InvalidOperationException("synthetic strict correlation refusal");
        var progress = new List<string>();
        foreach (var role in new[] { "supplier", "purchase-order" })
        {
            ProcurementFixtureOwnerCorrelation.PreserveOwnedScope(
                () => { ids.Add(role + "-owned-id"); volumes.Add(role + "-owned-volume"); },
                () => { if (role == "supplier") throw refused; }, errors);
            progress.Add(role);
        }
        Assert.Equal(new[] { "supplier-owned-id", "purchase-order-owned-id" }, ids);
        Assert.Equal(new[] { "supplier-owned-volume", "purchase-order-owned-volume" }, volumes);
        Assert.Equal(new[] { "supplier", "purchase-order" }, progress);
        Assert.Same(refused, Assert.Single(errors));
        var cleanup = new List<string>();
        foreach (var id in ids) cleanup.Add(id);
        foreach (var volume in volumes) cleanup.Add(volume);
        Assert.Equal(4, cleanup.Count);
    }

    [Fact]
    public void OriginalScopeFailure_IsNotSwallowedOrReplacedByCorrelation()
    {
        var original = new IOException("synthetic original scope failure"); var errors = new List<Exception>(); var correlated = false;
        var partialScope = new List<string>();
        var actual = Assert.Throws<IOException>(() => ProcurementFixtureOwnerCorrelation.PreserveOwnedScope(
            () => { partialScope.Add("already-validated-owned-id"); throw original; }, () => correlated = true, errors));
        Assert.Same(original, actual); Assert.False(correlated); Assert.Empty(errors);
        Assert.Equal("already-validated-owned-id", Assert.Single(partialScope));
    }
    [Fact]
    public async Task MetadataError_WritesDiagnosticThenFaultsCachedTaskWithOriginalReference()
    {
        var written = false;
        var owner = Correlation((_, _, _) => { written = true; return Task.CompletedTask; });
        owner.Record(0, "synthetic-private-metadata");
        var original = Assert.Single(owner.OriginalObservationFailures);
        var publication = owner.PublishAsync(0, "setup", CancellationToken.None);
        Assert.Same(original, await Assert.ThrowsAsync<InvalidOperationException>(() => publication));
        Assert.True(written);
        Assert.Same(publication, owner.PublishAsync(0, "setup", CancellationToken.None));
        var detached = owner.OriginalObservationFailures; detached[0] = new IOException("detached replacement");
        Assert.Same(original, Assert.Single(owner.OriginalObservationFailures));
    }

    [Fact]
    public async Task EventOverflow_WritesDiagnosticThenFaultsActualPublicationTask()
    {
        var written = false;
        var owner = Correlation((_, _, _) => { written = true; return Task.CompletedTask; });
        for (var index = 0; index <= ProcurementFixtureOwnerCorrelation.MaximumEvents; index++) owner.Record(0, "initialize-invoked");
        var original = Assert.Single(owner.OriginalObservationFailures);
        Assert.Same(original, await Assert.ThrowsAsync<InvalidOperationException>(() => owner.PublishAsync(0, "setup", CancellationToken.None)));
        Assert.True(written);
    }

    [Fact]
    public async Task ObservationAndWriteErrors_AllOriginalReferencesSurviveActualPublication()
    {
        var writeFailure = new IOException("synthetic write failure");
        var owner = Correlation((_, _, _) => Task.FromException(writeFailure));
        owner.Record(0, "first-private-metadata"); owner.Record(0, "second-private-metadata");
        var observations = owner.OriginalObservationFailures;
        var actual = await Assert.ThrowsAsync<AggregateException>(() => owner.PublishAsync(0, "setup", CancellationToken.None));
        Assert.Equal(3, actual.InnerExceptions.Count);
        Assert.Same(observations[0], actual.InnerExceptions[0]); Assert.Same(observations[1], actual.InnerExceptions[1]);
        Assert.Same(writeFailure, actual.InnerExceptions[2]);
    }

    [Fact]
    public async Task PendingWrite_LateObservationAndWriteFaultRemainOnSameCachedTask()
    {
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var pending = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var owner = Correlation((_, _, _) => { entered.SetResult(); return pending.Task; });
        var publication = owner.PublishAsync(1, "after-cleanup", CancellationToken.None);
        await entered.Task; Assert.False(publication.IsCompleted);
        owner.Record(1, "late-private-metadata");
        var observation = Assert.Single(owner.OriginalObservationFailures); var writeFailure = new IOException("synthetic late write failure");
        pending.SetException(writeFailure);
        var actual = await Assert.ThrowsAsync<AggregateException>(() => publication);
        Assert.Same(observation, actual.InnerExceptions[0]); Assert.Same(writeFailure, actual.InnerExceptions[1]);
        Assert.Same(publication, owner.PublishAsync(1, "after-cleanup", CancellationToken.None));
    }
    [Fact]
    public async Task ActualDuplicateRoleAndSessionRefusals_KeepOwnedScopeAndCleanupCallbacks()
    {
        var owner = Correlation(); var ids = new List<string>(); var volumes = new List<string>(); var errors = new List<Exception>();
        Docker.DotNet.Models.ContainerInspectResponse Inspected(string id, string role, string session)
        {
            var response = new Docker.DotNet.Models.ContainerInspectResponse { ID = id };
            var configProperty = typeof(Docker.DotNet.Models.ContainerInspectResponse).GetProperty("Config")!;
            var config = Activator.CreateInstance(configProperty.PropertyType)!;
            configProperty.SetValue(response, config);
            config.GetType().GetProperty("Labels")!.SetValue(config, new Dictionary<string, string>
            {
                ["maliev.codex.owner"] = "synthetic-owned-fixture",
                ["maliev.codex.run"] = owner.Identity.ResourceRunId,
                ["maliev.codex.role"] = role,
                ["org.testcontainers.session-id"] = session,
            });
            var settingsProperty = typeof(Docker.DotNet.Models.ContainerInspectResponse).GetProperty("NetworkSettings")!;
            settingsProperty.SetValue(response, Activator.CreateInstance(settingsProperty.PropertyType));
            return response;
        }
        var supplier = Inspected(new string('a', 64), "supplier", Guid.NewGuid().ToString("D"));
        owner.CaptureInspection("supplier", supplier.ID, supplier, "synthetic-owned-fixture", false);
        var order = Inspected(new string('b', 64), "purchase-order", "invalid-session");
        foreach (var (role, actual) in new[] { ("supplier", supplier), ("purchase-order", order) })
            ProcurementFixtureOwnerCorrelation.PreserveOwnedScope(
                () => { ids.Add(actual.ID); volumes.Add(role + "-volume"); },
                () => owner.CaptureInspection(role, actual.ID, actual, "synthetic-owned-fixture", false), errors);
        Assert.Equal(new[] { supplier.ID, order.ID }, ids); Assert.Equal(2, volumes.Count);
        Assert.Equal(2, errors.Count);
        Assert.Contains("Duplicate fixture provider role", errors[0].Message, StringComparison.Ordinal);
        Assert.Contains("Fixture session custody missing", errors[1].Message, StringComparison.Ordinal);
        var cleaned = new List<string>(); var invocation = owner.BeginCleanup();
        foreach (var id in ids)
            await owner.ObserveCleanupAsync(invocation, "observer", () => { cleaned.Add(id); return Task.CompletedTask; });
        foreach (var volume in volumes)
            await owner.ObserveCleanupAsync(invocation, "observer", () => { cleaned.Add(volume); return Task.CompletedTask; });
        Assert.Equal(4, cleaned.Count);
    }
}
