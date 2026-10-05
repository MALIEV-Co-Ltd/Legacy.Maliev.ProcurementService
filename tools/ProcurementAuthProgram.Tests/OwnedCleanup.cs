using System.Runtime.ExceptionServices;

namespace Procurement.AuthProgram.Tests;

internal static class OwnedCleanup
{
    internal static async ValueTask RunAsync(params Func<ValueTask>[] releases)
    {
        ExceptionDispatchInfo? first = null;
        foreach (var release in releases)
        {
            try { await release(); }
            catch (Exception exception) { first ??= ExceptionDispatchInfo.Capture(exception); }
        }
        first?.Throw();
    }
}

public sealed class OwnedCleanupTests
{
    [Theory]
    [InlineData(0)]
    [InlineData(1)]
    [InlineData(2)]
    public async Task FailureAtAnyPosition_StillAttemptsEveryOwnedResource(int position)
    {
        var released = new List<int>();
        var expected = new IOException("Synthetic owned cleanup failure.");
        var callbacks = Enumerable.Range(0, 3).Select(index => new Func<ValueTask>(() =>
        {
            released.Add(index);
            return index == position ? ValueTask.FromException(expected) : ValueTask.CompletedTask;
        })).ToArray();
        var observed = await Assert.ThrowsAsync<IOException>(() => OwnedCleanup.RunAsync(callbacks).AsTask());
        Assert.Same(expected, observed);
        Assert.Equal([0, 1, 2], released);
    }

    [Fact]
    public async Task MultipleFailures_PreserveFirstExceptionAndAttemptRemainingResources()
    {
        var released = new List<int>();
        var first = new IOException("Synthetic first cleanup failure.");
        var observed = await Assert.ThrowsAsync<IOException>(() => OwnedCleanup.RunAsync(
            () => { released.Add(0); return ValueTask.FromException(first); },
            () => { released.Add(1); return ValueTask.FromException(new InvalidOperationException("Synthetic secondary cleanup failure.")); },
            () => { released.Add(2); return ValueTask.CompletedTask; }).AsTask());
        Assert.Same(first, observed);
        Assert.Equal([0, 1, 2], released);
    }
}
