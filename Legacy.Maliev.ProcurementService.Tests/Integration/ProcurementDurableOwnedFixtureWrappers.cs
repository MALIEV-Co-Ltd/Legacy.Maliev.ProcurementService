namespace Legacy.Maliev.ProcurementService.Tests.Integration;

public sealed class DurableCreateOwnedFixture() : ProcurementDurableCreateFixture(ProcurementFixtureConsumer.DurableCreate) { }
public sealed class DurableChildCreateOwnedFixture() : ProcurementDurableCreateFixture(ProcurementFixtureConsumer.DurableChildCreate) { }
