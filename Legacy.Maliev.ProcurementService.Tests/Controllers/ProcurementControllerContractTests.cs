using System.Reflection;
using Legacy.Maliev.ProcurementService.Api.Controllers;
using Maliev.Aspire.ServiceDefaults.Authorization;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Routing;

namespace Legacy.Maliev.ProcurementService.Tests.Controllers;

public sealed class ProcurementControllerContractTests
{
    public static TheoryData<Type, string> Controllers => new()
    {
        { typeof(SuppliersController), "[controller]" },
        { typeof(SupplierAddressesController), "suppliers/addresses" },
        { typeof(PurchaseOrdersController), "[controller]" },
        { typeof(PurchaseOrderAddressesController), "purchaseorders/addresses" },
        { typeof(OrderItemsController), "purchaseorders/orderitems" },
        { typeof(FilesController), "purchaseorders/files" },
    };

    [Theory]
    [MemberData(nameof(Controllers))]
    public void Controllers_PreserveLegacyBaseRoutesAndRequireAuthentication(Type controller, string route)
    {
        Assert.Equal(route, controller.GetCustomAttribute<RouteAttribute>()?.Template);
        Assert.NotNull(controller.GetCustomAttribute<AuthorizeAttribute>());
    }

    [Fact]
    public void Controllers_PreserveAllThirtyLegacyActionsWithPermissionChecks()
    {
        var controllers = Controllers.Select(row => (Type)row[0]);
        var actions = controllers.SelectMany(PublicActions).ToArray();

        Assert.Equal(30, actions.Length);
        Assert.All(actions, method => Assert.Single(method.GetCustomAttributes<HttpMethodAttribute>()));
        Assert.All(actions, method => Assert.Single(method.GetCustomAttributes<RequirePermissionAttribute>()));
    }

    [Theory]
    [InlineData(typeof(SupplierAddressesController), nameof(SupplierAddressesController.CreateSupplierAddressAsync), "/suppliers/{supplierId:int}/addresses")]
    [InlineData(typeof(SupplierAddressesController), nameof(SupplierAddressesController.DeleteSupplierAddressAsync), "/suppliers/{supplierId:int}/addresses/{addressId:int}")]
    [InlineData(typeof(SupplierAddressesController), nameof(SupplierAddressesController.GetSupplierAddressAsync), "/suppliers/{supplierId:int}/addresses")]
    [InlineData(typeof(OrderItemsController), nameof(OrderItemsController.GetOrderItemsAsync), "/purchaseorders/{purchaseOrderId:int}/orderitems")]
    [InlineData(typeof(FilesController), nameof(FilesController.CreatePurchaseOrderFileEntryAsync), "/purchaseorders/{purchaseOrderId:int}/files")]
    [InlineData(typeof(FilesController), nameof(FilesController.GetPurchaseOrderFilesAsync), "/purchaseorders/{purchaseOrderId:int}/files")]
    public void CrossResourceRoutes_PreserveLegacyAbsoluteTemplates(Type controller, string action, string template)
    {
        var method = controller.GetMethod(action)!;
        Assert.Equal(template, Assert.Single(method.GetCustomAttributes<HttpMethodAttribute>()).Template);
    }

    [Theory]
    [InlineData(typeof(SuppliersController), nameof(SuppliersController.DeleteSupplierAsync))]
    [InlineData(typeof(PurchaseOrdersController), nameof(PurchaseOrdersController.CreatePurchaseOrderAsync))]
    [InlineData(typeof(PurchaseOrdersController), nameof(PurchaseOrdersController.DeletePurchaseOrderAsync))]
    [InlineData(typeof(PurchaseOrdersController), nameof(PurchaseOrdersController.UpdatePurchaseOrderAsync))]
    public void CriticalWrites_RequireLiveCriticalAuthorization(Type controller, string action)
    {
        var permission = Assert.Single(controller.GetMethod(action)!.GetCustomAttributes<RequirePermissionAttribute>());
        Assert.True(permission.RequireLiveCheck);
        Assert.True(permission.IsCritical);
    }

    [Fact]
    public void SignedPermissionClaims_AreAuthoritativeOutsideDestructiveAndPurchaseOrderWrites()
    {
        var purchaseOrderControllers = new[]
        {
            typeof(PurchaseOrdersController),
            typeof(PurchaseOrderAddressesController),
            typeof(OrderItemsController),
            typeof(FilesController),
        };

        foreach (var controller in Controllers.Select(row => (Type)row[0]))
        {
            foreach (var action in PublicActions(controller))
            {
                var httpMethod = Assert.Single(action.GetCustomAttributes<HttpMethodAttribute>());
                var isRead = httpMethod.HttpMethods.Contains("GET", StringComparer.Ordinal);
                var isDelete = httpMethod.HttpMethods.Contains("DELETE", StringComparer.Ordinal);
                var requiresLiveCheck = isDelete || (!isRead && purchaseOrderControllers.Contains(controller));
                var permission = Assert.Single(action.GetCustomAttributes<RequirePermissionAttribute>());

                Assert.Equal(requiresLiveCheck, permission.RequireLiveCheck);
            }
        }
    }

    private static IEnumerable<MethodInfo> PublicActions(Type controller) =>
        controller.GetMethods(BindingFlags.Instance | BindingFlags.Public | BindingFlags.DeclaredOnly);
}
