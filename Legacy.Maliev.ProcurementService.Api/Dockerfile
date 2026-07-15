# syntax=docker/dockerfile:1.7
FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
ENV GITHUB_ACTIONS=false
COPY nuget.config .
COPY .dependencies/ .dependencies/
COPY Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj Legacy.Maliev.ProcurementService.Api/
COPY Legacy.Maliev.ProcurementService.Application/Legacy.Maliev.ProcurementService.Application.csproj Legacy.Maliev.ProcurementService.Application/
COPY Legacy.Maliev.ProcurementService.Domain/Legacy.Maliev.ProcurementService.Domain.csproj Legacy.Maliev.ProcurementService.Domain/
COPY Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj Legacy.Maliev.ProcurementService.Data/
RUN dotnet restore Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj \
    -p:MalievWorkspaceRoot=/src/.dependencies
COPY . .
RUN dotnet publish Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj \
    --configuration Release --no-restore --output /app /p:UseAppHost=false \
    -p:MalievWorkspaceRoot=/src/.dependencies

FROM mcr.microsoft.com/dotnet/aspnet:10.0 AS runtime
WORKDIR /app
COPY --from=build --chown=$APP_UID:$APP_UID /app .
USER $APP_UID
EXPOSE 8080
ENV ASPNETCORE_URLS=http://+:8080
ENTRYPOINT ["dotnet", "Legacy.Maliev.ProcurementService.Api.dll"]
