"""Closed ordinary EF13 consumer; historical graphs and capabilities stay unchanged."""
import atexit
import ctypes
import contextlib
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

# BEGIN CLOSED CONSTANTS
MAIN = 'ebf0b2d77c5afde5844fdecdbb7dc53adf77393f'
MAIN_TREE = "8c9cd5a55f112b45eeae889d225cd6c2a63225b1"
ORIGINAL = {'.dockerignore': {'bytes': 335,
                   'gitBlob': '93eb303fe856a3343eccd4a5f81ed67e5b3319da',
                   'sha256': '9dcff9fae6bd9b9bbf1f4ea9593407a8ae5f2191951c46bfebde2e21a2ad5101'},
 '.gitattributes': {'bytes': 39,
                    'gitBlob': 'eb143e5370a2461f96f4610df1f6e30828c5639f',
                    'sha256': '91c171a7f4e295966f6e40aba83b0a11a56b4c99b59b9c55fcf54f15df207bc0'},
 '.github/dependabot.yml': {'bytes': 1189,
                            'gitBlob': 'fdb8f2d01a6ba1344f9cc7336055d049e2338ea3',
                            'sha256': '00c0921059adb3657db22507ce2df29e37505fbfebbe7992b9dc697630c384de'},
 '.github/workflows/_build-and-test.yml': {'bytes': 10563,
                                           'gitBlob': '362019e8979fd6268c439d9be724cb51fe7eb6ef',
                                           'sha256': '426f4a7e5b36a52f23b6799860b3115605af51e567659289ac27c13c982af1ad'},
 '.github/workflows/ci-develop.yml': {'bytes': 247,
                                      'gitBlob': 'c1bf874ecf39eab2864889fb4f2d8b38d1017bb0',
                                      'sha256': '55438892e1be3a3f5ff3e3e96aa69d74fc50884f1f465ce0ef1bc7e733ff825f'},
 '.github/workflows/ci-main.yml': {'bytes': 241,
                                   'gitBlob': '56aa263726fd6b3f767e4044c9037b0c7b54d7d5',
                                   'sha256': '4a5aeebe5da345b1fd15ff1a81197914a8bcd2fdb4c478bf04166ceeca273892'},
 '.github/workflows/ci-staging.yml': {'bytes': 246,
                                      'gitBlob': 'a069e91ab4fbd614302a6a1f73e1182a181ebb2c',
                                      'sha256': '5436292ba9523f34ca9f3801fdd674ed6e7d18b4e4d6e0b72bdb9c2d2fa1c1cd'},
 '.github/workflows/commerce-source-intake.yml': {'bytes': 2917,
                                                  'gitBlob': '6ec8c5005e07828aefb9f40d0c9f34e9e301fb80',
                                                  'sha256': '43b2464293f55f96d8a6e067119709f773df7aca7664e9387d3019940d414ab0'},
 '.github/workflows/pr-validation.yml': {'bytes': 293,
                                         'gitBlob': '49b784875dd9275866012396c3ff51a0b1f9dee2',
                                         'sha256': '8645e3bae51218b468c15c026360f8b2befd29813236e10d30def30bcee68cff'},
 '.github/workflows/procurement-auth-program-validation.yml': {'bytes': 3584,
                                                               'gitBlob': 'a1e63d16116e2468653845640b5cbb21177c6d48',
                                                               'sha256': '00532d335b48d1ef8c7c08cd567c11d13569f7816394ba9f67ac3bce2f6d843d'},
 '.github/workflows/procurement-defaults-owner-deadline.yml': {'bytes': 2267,
                                                               'gitBlob': '3559f1e7f466231ed569123e8ffd0e8a77b08f70',
                                                               'sha256': '2256f685463e4496a53bb1cb5f9e43542db75b209f0c095d489b874b39e12632'},
 '.github/workflows/procurement-file-metadata-binding.yml': {'bytes': 5370,
                                                             'gitBlob': 'a69ec42ad7ca662ed8cbe47b10109ddb30b87ca3',
                                                             'sha256': '4bd915baad206cfce16b7ac43e7dadb815bc5f6b89ed61421a4f4b068595f2f0'},
 '.github/workflows/procurement-header-ignored-fields.yml': {'bytes': 6482,
                                                             'gitBlob': '4bfecc0451accbf0a32e0b1a376a200a23dc90f5',
                                                             'sha256': '2a5a1d6d8c9ccb57c5adcc7083b2be34127a49e7588ed0cc7c2fad19c86c05db'},
 '.github/workflows/procurement-health-aliases.yml': {'bytes': 2480,
                                                      'gitBlob': 'c3e8a65839f44d60a291e2ab64fb423567a24309',
                                                      'sha256': 'a0cb07d8d265fe77b5cd99dea9204ca3a71159ea7e9a85c0054bbb247cceb51f'},
 '.github/workflows/procurement-lifecycle-focused-validation.yml': {'bytes': 2794,
                                                                    'gitBlob': '52df14a3f6905b7e6443ad490dbe46ab81d90e91',
                                                                    'sha256': '72026b3271e795fe5a24743af6563c8a60f6c9fd0d83b9db8e90467ddd10df8f'},
 '.github/workflows/procurement-literal-boundaries.yml': {'bytes': 2336,
                                                          'gitBlob': '0b03662ff4013dbca4abf49ed699360b0d0af321',
                                                          'sha256': 'b22d5a102487b0f698e6f86a6b1a8f0c01310548b7eee29cd3b22b74e87df731'},
 '.github/workflows/procurement-master-query-validation.yml': {'bytes': 2536,
                                                               'gitBlob': 'e9f8e78bd38746094a18210c8b4a7f592bb5c7fb',
                                                               'sha256': 'ee72aad2b4e66a0cbcc075a396089178319ca50df2246e2283d959ca496ac0b8'},
 '.github/workflows/procurement-metadata-identity.yml': {'bytes': 6386,
                                                         'gitBlob': 'def71e595a946d1ff7a7fe74fcc0ba640916872f',
                                                         'sha256': '153d8b1b9491536ec4aa377c741c1efb42e1d7a381cbeaa42e8b0ee12762df2d'},
 '.github/workflows/procurement-metadata-ignored-audits.yml': {'bytes': 6559,
                                                               'gitBlob': '2a5864e3f15f97ffd6b8eb5335dda36cc575780e',
                                                               'sha256': 'f143836d95615d378e28c2c0e5ba58f5c976ddbbbe4f2e9026a30aa7b35a840c'},
 '.github/workflows/procurement-nullable-sort-source.yml': {'bytes': 2261,
                                                            'gitBlob': '800609ac83accd77b9834e3f785ce2fba06155ba',
                                                            'sha256': '6521a20c8e70b23c9e67b50313241571048eee0d5305de26ed867efed2a3bdfd'},
 '.github/workflows/procurement-pagination-source-qualification.yml': {'bytes': 9045,
                                                                       'gitBlob': '24ea85ab07b69908026e92f7444755ec0bc03671',
                                                                       'sha256': 'ad1a36921a70949aba42a3709c4391cadc1fc3e94425319c040f2029c40c96be'},
 '.github/workflows/procurement-string-boundaries.yml': {'bytes': 2546,
                                                         'gitBlob': 'a43e13c07060e107986960d07f191ef4ba409dc8',
                                                         'sha256': 'd9e7ec70b4644a14194b07c1b16011528416722d082e171b9a4eae82f15eec7b'},
 '.github/workflows/procurement-supplier-address-causal-validation.yml': {'bytes': 5018,
                                                                          'gitBlob': 'bb72c837b0c9f9e0f16e7e61167218313b1c867f',
                                                                          'sha256': '1631f3c161b4e5c982107db1c5685f7cf9c1ec2298ebac87b3b3d6591ecbcb93'},
 '.github/workflows/procurement-supplier-identity.yml': {'bytes': 6468,
                                                         'gitBlob': 'b85d9a641345b69e0e2cb2f006b80511ed6b45cc',
                                                         'sha256': '5761be7389a4eb085c84ae2eb9597c167c430c57106a919e733777765160aaa3'},
 '.github/workflows/procurement-supplier-ignored-audits.yml': {'bytes': 6575,
                                                               'gitBlob': '2a274d3e9c0272a76cdf5516e034a5b314ff2223',
                                                               'sha256': 'db4acafd90548d1c8f0a11dd14e9e8f0375a799a0b3f8c6976e98372c05f9ffa'},
 '.github/workflows/publish-image.yml': {'bytes': 1279,
                                         'gitBlob': '226d1c7964c798b2d5d2018bb6ec521212eb3090',
                                         'sha256': '1f8789e555794dd7f0785cc1086f1db71609a43a6fe47f60d14ee5267bc08482'},
 '.github/workflows/supplier-address-parent-audit-source.yml': {'bytes': 2410,
                                                                'gitBlob': '394e0d3efb74dce7b8a4a01794c32a429c560e4a',
                                                                'sha256': '01f42c76d6e5ca807fe9ea5a90e8bca5812d6fabd6fb0d5515e78b9549166038'},
 '.gitignore': {'bytes': 124,
                'gitBlob': '1669114d7fb2bda83281049aa9e624dc24627c4f',
                'sha256': '119830ec1543e7d524a8c24f1414cceb81c4db869b3e3fcf095f1dd29a48c61c'},
 'AGENTS.md': {'bytes': 1975,
               'gitBlob': 'e2ffb807c7309a0499b91dd28db71dfb0e6774d0',
               'sha256': '075322946439684a0d368d1fbcff2694f160fa7cd19ecbb0f38be35a8f32ca75'},
 'Directory.Build.props': {'bytes': 515,
                           'gitBlob': 'b47c8d23651f11ea8366bb63f4520fb8de6c6df3',
                           'sha256': 'b03b93e505f9bd0f5d396c5041d9b35d6cfccb454384ba8151e55e05edf45083'},
 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementIamComposition.cs': {'bytes': 4660,
                                                                                     'gitBlob': '1bad18d6797295124d84083ba7f5e93276124c1e',
                                                                                     'sha256': '730e0cfde2314b27403f3ed15e653d4436b06e268070b134e93e198ca9ba3d34'},
 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementPermissions.cs': {'bytes': 3010,
                                                                                  'gitBlob': '58a5a184edc50559048dd4b0329b80b5a6a57b5f',
                                                                                  'sha256': '4af69a3b4f4c5ab015ac861370ab0d2064503e26432dd19f5011b9a802a59abb'},
 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementWorkloadExchangeGuard.cs': {'bytes': 5240,
                                                                                            'gitBlob': '2cbafd5644b7653a1eb323788be8f95bd98337ad',
                                                                                            'sha256': 'dd7a1fe2ff08469f877ccde6f6d9f41594b248ddb23b48ca17586d8cd454e264'},
 'Legacy.Maliev.ProcurementService.Api/Controllers/FilesController.cs': {'bytes': 4444,
                                                                         'gitBlob': '5382d06a862ff843bbb01539ddd8822070e86757',
                                                                         'sha256': '813db30a96a4b1555d78d31350f1b50cd520f3598359cc2727e0c717757abb67'},
 'Legacy.Maliev.ProcurementService.Api/Controllers/LegacyProcurementHealthController.cs': {'bytes': 1990,
                                                                                           'gitBlob': '4d81008ab101f21125dc4c6da7146453cc343bbf',
                                                                                           'sha256': '559531d9d7badf5dd2111dfeb2a9872c45eefd3256d2a89c869a9135c16229f9'},
 'Legacy.Maliev.ProcurementService.Api/Controllers/OrderItemsController.cs': {'bytes': 3532,
                                                                              'gitBlob': 'd5e94258bed07bff6c4c915ab4cb1e34fa368902',
                                                                              'sha256': '5abd51a278d24b317122fc758ac71079be8f2e1ae3c79c1fbd3895c1936a6121'},
 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrderAddressesController.cs': {'bytes': 3157,
                                                                                          'gitBlob': '4c7704ebc099c3e6cc2ee3596cbcc847d348ff16',
                                                                                          'sha256': 'f8fd7ed36a895cc78612ccff8226730a3c05311b3ccc180a515dcdb82b83cf8a'},
 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrdersController.cs': {'bytes': 4158,
                                                                                  'gitBlob': '19530897851dcd97dbf52ee71d297f0b4cd0517c',
                                                                                  'sha256': 'a2c176ba75037413518e1a6583ca12ff1e9b13ecf14887f7d2dceaff7e6ab848'},
 'Legacy.Maliev.ProcurementService.Api/Controllers/SupplierAddressesController.cs': {'bytes': 3971,
                                                                                     'gitBlob': '2b0028e2498e1255203b17f74a62a9d4023a9c46',
                                                                                     'sha256': '1ecbe0590f07de2670a340eba5827f0e8a590de2caa2d0b5cdac08b3daa44ddf'},
 'Legacy.Maliev.ProcurementService.Api/Controllers/SuppliersController.cs': {'bytes': 4087,
                                                                             'gitBlob': 'f010e662b533449c49f8080be48ceb0a7dcfdc0f',
                                                                             'sha256': '24e5b3879cd790eece7f7a91caa3d2ac92769958b884c08b57d03ce12b0b9fb2'},
 'Legacy.Maliev.ProcurementService.Api/Dockerfile': {'bytes': 1330,
                                                     'gitBlob': 'b2c525d395006937f2faf1dbbe0ffa53b669e6d0',
                                                     'sha256': '34bb4f012e49dc09e03390cd383402aa56fbe72062ad57b86350ad7f14a68793'},
 'Legacy.Maliev.ProcurementService.Api/DurableChildCreateEndpoint.cs': {'bytes': 2984,
                                                                        'gitBlob': '84b6da4468a7a22ae10d81aed8b29f6dab15dfaf',
                                                                        'sha256': '8e09a36779eee8b5b844b391e3d6a9c8ce5ba083a21dac0d1ba03d5af627b283'},
 'Legacy.Maliev.ProcurementService.Api/DurableCreateEndpoint.cs': {'bytes': 4364,
                                                                   'gitBlob': '4a723a638129fbdb99a17758a06a8cd5c3f026ac',
                                                                   'sha256': '179bbadd53d3909a41fe08892b80df44b41cf9483333117c98859cad406c2c2e'},
 'Legacy.Maliev.ProcurementService.Api/IdempotentCreates.cs': {'bytes': 795,
                                                               'gitBlob': 'c8a0e7f92a10b833cd5a5254b0253f7537b67074',
                                                               'sha256': '14c9a0608a7e3f9c55a4ef98ce29c949ebb298c0f81ead3ccea1c56b6e7f5f63'},
 'Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj': {'bytes': 1572,
                                                                                      'gitBlob': '30c131eb10c554b445e878c0b148cbe79d8c7cd3',
                                                                                      'sha256': '27bbc5f9f020fde78ff975ad1bc653fa117eb822d3e32f981901b0e43cac5126'},
 'Legacy.Maliev.ProcurementService.Api/Program.cs': {'bytes': 4286,
                                                     'gitBlob': 'a82fb0b60ca92d2df1a39a3b82eaecdeef1f7505',
                                                     'sha256': 'a19bf446003715e73ab5161eda4c884e80a06ad2c12d0d23a5be6d670286720e'},
 'Legacy.Maliev.ProcurementService.Api/Properties/launchSettings.json': {'bytes': 618,
                                                                         'gitBlob': '5b49ab6aa8f800b7ed4a376abb9ccf0942625251',
                                                                         'sha256': '3d5744d3d6ffce5b0a1a1b30d81543bda5ddc6146fd7ee9d1592c3b769210a40'},
 'Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs': {'bytes': 11126,
                                                                                               'gitBlob': '112e92787f4c07d47cf0caa404abb392a3d8563b',
                                                                                               'sha256': '77d6145f30de7f47b9248eef11416efad888c315ab55ab572aaff23a8c07fe26'},
 'Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementOriginalBodyModels.cs': {'bytes': 6445,
                                                                                         'gitBlob': 'e352494ce31eb5bead53a78cc4c950a7bae3e54e',
                                                                                         'sha256': 'bf51171f980f1e56a7023317c98a2313275d05d976264471d9df7ede65efc96f'},
 'Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementSourceBodyInputFormatter.cs': {'bytes': 8072,
                                                                                               'gitBlob': '942a1b8f8f18ea3a9727691a05a784aec688614d',
                                                                                               'sha256': '65a05334d787e1f35031b72df13b59e43f2abd6046eaf898fe3122bf8cda6cc2'},
 'Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderFileMetadataRequestJsonConverter.cs': {'bytes': 1627,
                                                                                                         'gitBlob': '3aca6cb413f13945efc28e9e2cebeafbe351d8f3',
                                                                                                         'sha256': 'e7dae18e5cc6095eda6444239532455e85c8de3c359dc0514797cccf478e80f0'},
 'Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderHeaderRequestJsonConverter.cs': {'bytes': 8846,
                                                                                                   'gitBlob': 'b21e6fe697acdeb945dc0acbd3c80dee22a23a02',
                                                                                                   'sha256': '08acc76e39ad164565efdd4d61690c84fda773fd2067535812b95ece0d72fdbc'},
 'Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs': {'bytes': 4033,
                                                                                          'gitBlob': '87fd40bbe9072c8da0cc3567020d2872b05a107d',
                                                                                          'sha256': 'f3a83e73608ab207e41e3b9e7d3c47fb5da0c08232ce7ec786043574cf5e8f9b'},
 'Legacy.Maliev.ProcurementService.Api/appsettings.Development.json': {'bytes': 119,
                                                                       'gitBlob': '0c208ae9181e5e5717e47ec1bd59368aebc6066e',
                                                                       'sha256': '817db0bf2ecca78364c41dbaf7949bf2504cf47a1c3d0d54f3be8178fefc030b'},
 'Legacy.Maliev.ProcurementService.Api/appsettings.json': {'bytes': 398,
                                                           'gitBlob': 'b057873ee272efdfc5311a0179a6214f4e1768b7',
                                                           'sha256': 'd23c8ea8e5ec65dc0425ed341a99eb2d4460bc922b42a45b8201ddb6a68d3442'},
 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementChildCreates.cs': {'bytes': 877,
                                                                                                'gitBlob': 'b3cda03315eb9e70d9264a5a50fbdbfeef6c3705',
                                                                                                'sha256': '6a4ecbf64a7ec283a3391ad9eb6c696e0930859527b8db9f285a84e240d71322'},
 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementCreates.cs': {'bytes': 810,
                                                                                           'gitBlob': 'b91e35948db367bb5279029e5838a0e87617041c',
                                                                                           'sha256': '13e8791df7ade5ddbbb2e143bf6f07aaa669cf531771792d76d48dd202bb6464'},
 'Legacy.Maliev.ProcurementService.Application/Interfaces/IProcurementBoundaries.cs': {'bytes': 12036,
                                                                                       'gitBlob': '7d5f584a13022c56b13e4517748cc772658ba74c',
                                                                                       'sha256': '08aee896e0c774b7e5d0587709fb3e0b56959c1a5f6c463d15ed45c2d73e51cd'},
 'Legacy.Maliev.ProcurementService.Application/Legacy.Maliev.ProcurementService.Application.csproj': {'bytes': 482,
                                                                                                      'gitBlob': '8f5ac62cbd3b2f8cf8370a899a575e25d4a07dab',
                                                                                                      'sha256': '242674f76261bb05fc8e079c764a4e53c5c82c187a7f039b968b1d6e883a6ab8'},
 'Legacy.Maliev.ProcurementService.Application/Models/DurableCreateModels.cs': {'bytes': 1166,
                                                                                'gitBlob': '6fce05a93ea834e1fc661e0938456e92b908a003',
                                                                                'sha256': '0928b477c3ab8b58808368a9ff44a85a39281b3e731300b5078a741a40e338c1'},
 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs': {'bytes': 7105,
                                                                              'gitBlob': 'f20b6e2ac31e8a4e91567fca14cf6af449e3b3f0',
                                                                              'sha256': 'cb0e10f9eecf82f64fb389929c0c53a82b8461d3af918572fece2f4dbe51d679'},
 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementTransactionUncertainException.cs': {'bytes': 423,
                                                                                                     'gitBlob': '6486a812e5e78ae8e8be9bcf54ee8683989e0615',
                                                                                                     'sha256': '5939e09abe4ddfdf0f48e77299cd3193f1401a62146958e5c8eda16016bebbf9'},
 'Legacy.Maliev.ProcurementService.Application/Models/PurchaseOrderAddressScalarStringJsonConverter.cs': {'bytes': 1736,
                                                                                                          'gitBlob': 'cdbfc2e43f4d8575006df249836145cf7ecb50d6',
                                                                                                          'sha256': '5daa71d1438641039589d708471e65d42de8e8ff1f2807416315eef409ec3ecf'},
 'Legacy.Maliev.ProcurementService.Application/Models/SupplierAddressScalarStringJsonConverter.cs': {'bytes': 1825,
                                                                                                     'gitBlob': 'a450e196d981d66aef98b6a5970e6f1f53bcef67',
                                                                                                     'sha256': '488b35a991d7310bf1d4737e35e2a0beaf032a598e06c84c33c3ffe4246d7db7'},
 'Legacy.Maliev.ProcurementService.Application/Models/SupplierScalarStringJsonConverter.cs': {'bytes': 1794,
                                                                                              'gitBlob': '25834e7c9705786777a707734b914fbf99987cfc',
                                                                                              'sha256': '745bc4e2f90e646b6a5b28286c995b6cc67dc2e3ee036d644e40d71d033c7681'},
 'Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs': {'bytes': 8328,
                                                                                             'gitBlob': '28204fc1402f836d1da3ae94542bb5ce249b1c1b',
                                                                                             'sha256': '838f3b9ad6392c1eb5471f2fcd070ec7c29adac43553c12472b4b656495d2af3'},
 'Legacy.Maliev.ProcurementService.Data/ChildReceiptRecords.cs': {'bytes': 1972,
                                                                  'gitBlob': '8974e76d5c72762828a0d32624a09faaafe8dda4',
                                                                  'sha256': '31e104d96b383995c0ea20b4cfb0ec42f0c91f2e960364b22a7f5e6747de3495'},
 'Legacy.Maliev.ProcurementService.Data/CreateReceiptRecord.cs': {'bytes': 2215,
                                                                  'gitBlob': '7df3a2a661854d928fb4ac6363596546419ffeb3',
                                                                  'sha256': 'bf5efa39a007eb20be00d2bdcfa08768ea8f8ca1553c916ba534f4d6937e7c91'},
 'Legacy.Maliev.ProcurementService.Data/DistributedProcurementCache.cs': {'bytes': 2947,
                                                                          'gitBlob': 'cd88f078148dadf470850b383874f2453c3ab146',
                                                                          'sha256': '177ceb574312365499b77fa3f417b1b574ad6cea4aae5773d8708d0cce011d21'},
 'Legacy.Maliev.ProcurementService.Data/DurableProcurementChildCreates.cs': {'bytes': 12064,
                                                                             'gitBlob': '0fe45073973624adcf21d6abcef8a23ced035f97',
                                                                             'sha256': '78062f135674bdf5e939ef92d9ae45a678e8e71c5ae1ac911d806e5224d12887'},
 'Legacy.Maliev.ProcurementService.Data/DurableProcurementCreates.cs': {'bytes': 7916,
                                                                        'gitBlob': 'd8e7d7f4182fc613a399990acf9109f0ca7a9e3a',
                                                                        'sha256': '059bf4f8a99c2c6bdeb40219b4101a27789baa71c8cf12b935da6898c1261b1b'},
 'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj': {'bytes': 1182,
                                                                                        'gitBlob': 'c152c047af1ddb1bcedccf08b25d6a03320d34f3',
                                                                                        'sha256': 'd30612eef15d7e780e32dde8d14f4e7ad1ba821cc553f72a7e16930322185161'},
 'Legacy.Maliev.ProcurementService.Data/LegacyUtf16StringStorage.cs': {'bytes': 1381,
                                                                       'gitBlob': '2e68e9f383160dfe6082f7a23b859bfbf5b2d325',
                                                                       'sha256': 'bb8d7dc5fe86ef1aa33f960c7063ad50e4659e93608add55dcd54305524c92a7'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.Designer.cs': {'bytes': 13207,
                                                                                                                                         'gitBlob': 'ff647d92152d6acaa1b5d54c2381711263a6e38a',
                                                                                                                                         'sha256': 'f3c9a57094fe51c54eb58b53471778776521ae79e15c4b21d385cd062d7b32de'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.cs': {'bytes': 9438,
                                                                                                                                'gitBlob': 'f27917f143b0cbdf2809881b96c2ccce3b4dccb8',
                                                                                                                                'sha256': '03301e6f3b2c70983f2e87c94eb5a146edcff5d0f4f608e61942e992ea5afe4f'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.Designer.cs': {'bytes': 13345,
                                                                                                                      'gitBlob': '2e9588ac6e0a9da4feaa4fb59a683f785560c713',
                                                                                                                      'sha256': 'df5ab1ddad179047b7152518eb21aaffee4706438f46fe6a7354739142285273'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.cs': {'bytes': 1906,
                                                                                                             'gitBlob': '86049cb052f1390dad51c9800f301d2af411a87f',
                                                                                                             'sha256': 'ffb91646968102e48858dab840bb7c05365e201ac211493255cb7f423097eaeb'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.Designer.cs': {'bytes': 15803,
                                                                                                                                     'gitBlob': '9ab941b4fbbc26b1bf4277328792cc594936e7ca',
                                                                                                                                     'sha256': '3f2b9ff40c627b0e7972efc173e9fbe1eabfd7ec59435b4d792841132a276d27'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.cs': {'bytes': 2701,
                                                                                                                            'gitBlob': '8b1f910f078b8a4d13f15c6903a9825e0198bbbf',
                                                                                                                            'sha256': 'ce40e219e5a195a5a5f4f78df44d82e97b7e5e100fe2e9b771e897364d5bb2e9'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.Designer.cs': {'bytes': 20076,
                                                                                                                                           'gitBlob': '143e1ae02a1fd1100eb2d75dce9b8124188e4cd4',
                                                                                                                                           'sha256': '02b39a5cd8a0d7bede249eedac89633d77f232fb3babed2ea2c63f12088c52f5'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.cs': {'bytes': 7985,
                                                                                                                                  'gitBlob': '1663bacce0bf61de8db5688a82e48354c24ba658',
                                                                                                                                  'sha256': '67e8bca2aecc8c13dfaf15bcd28feeb73cad3ba0b2d99ebb050883ee0c6f2a01'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.Designer.cs': {'bytes': 24927,
                                                                                                                                    'gitBlob': '71271d8755686ea6609b0d794484ec8ae29e41eb',
                                                                                                                                    'sha256': '2666ab8dc452e07ce8f80637bb9858e3d150a6ec1cdc2fd8e80efefc75d684e8'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.cs': {'bytes': 2823,
                                                                                                                           'gitBlob': '2ba84b62673cd157fd53807eeb21bb9c59375422',
                                                                                                                           'sha256': '03088284cdabe2c0e4954275d42879276eb7551d2dfbf30076fac6f8ef998d21'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/PurchaseOrderDbContextModelSnapshot.cs': {'bytes': 24790,
                                                                                                           'gitBlob': 'b3477b7823f63b37bed92959f7100e3cd287baf9',
                                                                                                           'sha256': '52c5bae2143d22161a609f03b212ce321699728be55df592816e952d8492d28d'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.Designer.cs': {'bytes': 6225,
                                                                                                                               'gitBlob': '84c0f1841ecd125e52dbdd8fff6d560cf26baab7',
                                                                                                                               'sha256': 'd5bfa2472a2078c0bdcf1c351463f1df8405d60ea154f22cd3241c7efc92cd3b'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.cs': {'bytes': 4432,
                                                                                                                      'gitBlob': '2d36ff6600a6c973baf717fe07c61e72a3cad80e',
                                                                                                                      'sha256': '4a71fe849edb3af05e0b651b62aed2f6c5420b94557ec21708b5511b1e914608'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.Designer.cs': {'bytes': 6285,
                                                                                                                 'gitBlob': '7edb0df2fe539c86629d0296e95ae428506d2a90',
                                                                                                                 'sha256': 'c5b64ab25e0551684838fafbd266c124ffc29bdc4442e77e7943872a15007e5e'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.cs': {'bytes': 1721,
                                                                                                        'gitBlob': 'f6c70ffcb468140850659ff2dee07290d5b891b4',
                                                                                                        'sha256': 'f3061887f77e600e49bb779af6e004059c703bdfde7c4b08ec4c90a998cef9ea'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.Designer.cs': {'bytes': 8703,
                                                                                                                           'gitBlob': '022a0c30e60b669e22b310ba6f589244f4d004fa',
                                                                                                                           'sha256': '2b192c95822c18916d93e40e5342d21c81cb390dda15c6c44311671971935190'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.cs': {'bytes': 2661,
                                                                                                                  'gitBlob': '653202333c192a7c96844f639858f9e362524d77',
                                                                                                                  'sha256': '21e9659b30e9907d0deb78593294eabe79a1558504b10633f97085786f109ee1'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.Designer.cs': {'bytes': 11405,
                                                                                                                                 'gitBlob': 'a36060169d6812f83f1fe764faddc0c0eeee2fea',
                                                                                                                                 'sha256': 'f215f333d633b30156f84f151d8453eb87f11a32e9be3eb10e672e3a3ae770ac'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.cs': {'bytes': 6084,
                                                                                                                        'gitBlob': '8c82219082c3a6f2bb629a65d72d8a459b07b5d4',
                                                                                                                        'sha256': '1dd0bf5955b23f627b7c4820723a03fcf5607c265b98120f7f4b10b695df5cd3'},
 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/SupplierDbContextModelSnapshot.cs': {'bytes': 11259,
                                                                                                 'gitBlob': 'e77cced2826569ba96cb46d659e0fb90be8ceb0e',
                                                                                                 'sha256': 'f902c87617ea1da7a1c376e34ea747c63362912cfca3199d4214a6d9abc2d4fd'},
 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContextFactories.cs': {'bytes': 1307,
                                                                            'gitBlob': '0eadcec30749cdccde9c4a8eae39e5f9c9a0ec80',
                                                                            'sha256': 'a7dd48f0b8ed1e3eb89690e0678eb3d16711767bf803a9e11706061dd17b2463'},
 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContexts.cs': {'bytes': 10046,
                                                                    'gitBlob': '1a8487f24a647a186258d487b84e1cc08fa7d83b',
                                                                    'sha256': 'cc5e7d769d39093a83e67f64b032a95f8bb88a53e73bf2a9a515d9a9e69a02c2'},
 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs': {'bytes': 24843,
                                                                      'gitBlob': '54cb841a000af128f8cac90028966577983f3228',
                                                                      'sha256': '3677049303f907ab18a017575f481fba0a18b8cbd173a3d21ec737fa92ed56a4'},
 'Legacy.Maliev.ProcurementService.Data/PurchaseOrderFileSourceConstraints.cs': {'bytes': 423,
                                                                                 'gitBlob': 'c182f47f50e92fd3225c08d14bcb505e49d73ad5',
                                                                                 'sha256': '2c6d42895cbc600c0c0ef116fa8f3e15901bd605f1f57c9be3bc1fa71f2f056a'},
 'Legacy.Maliev.ProcurementService.Data/ReceiptReadiness.cs': {'bytes': 4931,
                                                               'gitBlob': '7e252a2a88928f12d421b10fe7cf831146268b9d',
                                                               'sha256': 'fd18f524bd30f2b00b282801a9e330987bbd3579829ffe45419db705938837ec'},
 'Legacy.Maliev.ProcurementService.Domain/Legacy.Maliev.ProcurementService.Domain.csproj': {'bytes': 327,
                                                                                            'gitBlob': '51addf44ecf979d69d9d77527d402f14c06a4fa5',
                                                                                            'sha256': '0aec8d23fc31d062753209091db0c1b51aef9b67e0ed3626bf0dee66e38dc118'},
 'Legacy.Maliev.ProcurementService.Domain/ProcurementEntities.cs': {'bytes': 7931,
                                                                    'gitBlob': '141a05708c3374afe8ad9471698a892addbf2531',
                                                                    'sha256': 'ed853669f5ea4c72b80aa2cc8d994f2a3cf795c86c63a7f924e8717d2932fbd1'},
 'Legacy.Maliev.ProcurementService.Tests/Application/ProcurementApplicationServiceTests.cs': {'bytes': 4566,
                                                                                              'gitBlob': 'e50a343850c2ef2357e9eb0d29c7ee74c5855717',
                                                                                              'sha256': '384dc735761f239f2fe0822a1878792117204d881b2468eed923285fe7801fae'},
 'Legacy.Maliev.ProcurementService.Tests/Caching/DistributedProcurementCacheTests.cs': {'bytes': 4416,
                                                                                        'gitBlob': '958df218aae0a34e0ce451008c31efc3181a28a6',
                                                                                        'sha256': '14e5e616659a54b834f3b75d3fc286a2182a82bcb01a73f79331e7326777972e'},
 'Legacy.Maliev.ProcurementService.Tests/Controllers/LegacyProcurementHealthHttpTests.cs': {'bytes': 14011,
                                                                                            'gitBlob': '50a8f89f606f574985eb259648158de75bb62b0e',
                                                                                            'sha256': '4e62e3218928bffa759130527149bcd48da1c30fee6ba52951bb50f530688152'},
 'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementAddressNullBoundaryTests.cs': {'bytes': 5362,
                                                                                               'gitBlob': '43a7688f76cfe4a8b19d1e7171e070aaa6c31226',
                                                                                               'sha256': '7a5e7f4c5361791bd17071d5a33769d9a709e218699ae5e10b5cbc723972252c'},
 'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementControllerContractTests.cs': {'bytes': 5005,
                                                                                              'gitBlob': '5cf23fcc448277d5a4fe86ac4fc5749502604de9',
                                                                                              'sha256': '8f8d8b32d34262a20f97cd5f4627d14d544e216c0c052897c49b47977c9e3286'},
 'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementOpenApiHttpContractTests.cs': {'bytes': 13666,
                                                                                               'gitBlob': 'eb9a3cc0f299279ad4db1f305dd86519d69f5429',
                                                                                               'sha256': 'c497f82e1793ebd778ebd804db2cbeea6d0ec202d7b4e542361dcddab3109a11'},
 'Legacy.Maliev.ProcurementService.Tests/Controllers/ProcurementSupplierMutationSourceTests.cs': {'bytes': 4075,
                                                                                                  'gitBlob': '8a4f380fdba53512b48bb8e4c864f67ccc84584f',
                                                                                                  'sha256': '69ea2a807c3a9715e04c8b2aedafc3ed93d24331402ac5b4155d236c22f4456e'},
 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementModelCompatibilityTests.cs': {'bytes': 2823,
                                                                                       'gitBlob': 'e0c5f86b10f9f8b0208fe3c4ab3117c0bb4b78e1',
                                                                                       'sha256': '05b27d74d9dcec6f69f5dd5781e6fb908267d307955fa11f1a9972660618c18f'},
 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementPostgresMigrationTests.cs': {'bytes': 6651,
                                                                                      'gitBlob': 'c8c60dc1cf1fd050536bdffd35328605a9fe4147',
                                                                                      'sha256': '3a54b2d4c0c5fbbff249851397a4c511e5b0abe16f9374948519e809219b082f'},
 'Legacy.Maliev.ProcurementService.Tests/Data/ProcurementSourceStringMigrationTests.cs': {'bytes': 17605,
                                                                                          'gitBlob': '76a43cbe0d3d8fbb06a5067d8c8c7d3f1292e2e3',
                                                                                          'sha256': '2c1666b9f59adeb7c4e9e58f42e11c833702cb4abb01a9d663553e1661885065'},
 'Legacy.Maliev.ProcurementService.Tests/Data/TimestampMigrationContractTests.cs': {'bytes': 2434,
                                                                                    'gitBlob': 'aa609d2b04d574a7869bee7fa102e232de05450c',
                                                                                    'sha256': 'f6a3d4446ccb85bac559ee56ce5d1e2ea5870fd8fd1775fbbf5c030bfd117e66'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/HistoricalNullableSupplierModelCustomizer.cs': {'bytes': 790,
                                                                                                     'gitBlob': '57bfd8f09b3a0dd115e827b94d9dc466aa02d79e',
                                                                                                     'sha256': 'f65f8096ce4c71beab2247f9a37607debd157ba489bc4807c42617559af4e2ce'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementAddressAndFileCreateLiteralSourceTests.cs': {'bytes': 6014,
                                                                                                             'gitBlob': '887aac7c745dd09b7617aa656683c66f0e1f2720',
                                                                                                             'sha256': 'fafbd6c9d093ce6346bad827cfab7e565b8df6f8e355054b4e9d58b4eddc853f'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementAddressCountryIdBindingTests.cs': {'bytes': 29410,
                                                                                                   'gitBlob': 'b21c6970729ad6c7982d4a361ab81131d35a8120',
                                                                                                   'sha256': '7cc2dd94b9d81d8d7e235bda892a4b819947e97ea4442c33661dae39f049bd24'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementAddressLifecycleTests.cs': {'bytes': 23785,
                                                                                            'gitBlob': '5b672d53ada565182ef4656acbeb82cb40b8211f',
                                                                                            'sha256': 'b374f905c5973e66c7d7bfbfdbceee136e95c13c6f7fc36f344b1c9509225f63'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementAuthenticatedIamTests.cs': {'bytes': 19871,
                                                                                            'gitBlob': '5120d29dab2cc55c2b808ad25346b92c4a3ee7bc',
                                                                                            'sha256': '7ceee7178d81351bc2d96eb31a0720eb908c2721b5c63d377cd62efbdbfa47f9'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementChildLifecycleTests.cs': {'bytes': 13526,
                                                                                          'gitBlob': 'f9b4e2b337d1e2dce1f94a9c68c18f22ab444456',
                                                                                          'sha256': '2516124df5029a659fdb9a7e04d508a40ad9e835ff1f3eb0188d7e96da63be6e'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDefaultsOwnerDeadlineTests.cs': {'bytes': 16187,
                                                                                                 'gitBlob': 'ab0a6f8420e95c6cfb824b465db3f174237ee8c7',
                                                                                                 'sha256': '29e438a64eeb7c166e3b69bc42e80578861479ac8d3151ca84a4590ae7b7a0de'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableChildCreateTests.cs': {'bytes': 28333,
                                                                                              'gitBlob': 'b482c7ed604319943b17c20ced3c63784423108e',
                                                                                              'sha256': '267bd3842c55c5fce14ec4f0bd4de16351eeb1b4c9409e056b5ab3d7cb3ff541'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementDurableCreateTests.cs': {'bytes': 57381,
                                                                                         'gitBlob': 'c1ec0caa917ceb784142f28dc499c3ec61532258',
                                                                                         'sha256': '187bc8a0ffb8aa9ca6eb6f8597f59620b0e6bcba4aaff699170de9b2849eccc3'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementHeaderIgnoredFieldsTests.cs': {'bytes': 25553,
                                                                                               'gitBlob': '9511b108f50ffc625b4cb97caf04b57a926c03c6',
                                                                                               'sha256': '2eaa4ea3206710194cdcc4383d3c0d9110de6a242d427a8d8e862604c1b888cd'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMasterQuerySourceTests.cs': {'bytes': 22080,
                                                                                             'gitBlob': 'e29fcc568be0d5b378c9a941484f9bda26d64b31',
                                                                                             'sha256': 'f23e6981bfb575d27d2b318c291c8c817ec97d878a0b8ae73ede2dc2563cf914'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataIgnoredAuditDateTests.cs': {'bytes': 29599,
                                                                                                    'gitBlob': 'd1f80a5bf248ae8dd51de591221a3fa3a3ace1c5',
                                                                                                    'sha256': 'c3b13c0db0e24b4db11a8bdef05aba3f206c3e5af8e52e396022e73497fc1ae5'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataIgnoredBodyIdTests.cs': {'bytes': 26393,
                                                                                                 'gitBlob': '2447ea79cf8e1b5692feea9479cb6beccafd18fc',
                                                                                                 'sha256': '6a2698da0cdfaace053d68340f97871934df9de30df1d36b4318f0c1fe02e223'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataOriginalModels.cs': {'bytes': 6295,
                                                                                             'gitBlob': '0f1751b705cf1b41fd3e7a489534eacece6e3e64',
                                                                                             'sha256': 'c74927f65af90ecacf2a76f4fd5ccc5c661c7494719b9cb9d28d00e2d2d1d04a'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataSourceOracle.cs': {'bytes': 6105,
                                                                                           'gitBlob': '26950761aedd6be196e09f04a02ab99565f5dcf6',
                                                                                           'sha256': '047605dd225a0052192f9f7adb6c19c8cdd9aa4b93524429c31154041a234cba'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementMetadataSourceProtocolTests.cs': {'bytes': 15474,
                                                                                                  'gitBlob': '16ce05f77ec4d3ca655046dbc76fbdfa0d92edad',
                                                                                                  'sha256': 'e5f51e493f42c38b12309ce0a7242276acabf5eb628b99c2697bddbeac1d79e7'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementNullableSortSourceTests.cs': {'bytes': 8784,
                                                                                              'gitBlob': '10448e793f4d4092471f584f02e4220d8181b12c',
                                                                                              'sha256': '9cd7177aa34a589d483e81752c00d2ceb464e71dfb06d209f80462294c136f12'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementPurchaseOrderAddressScalarStringTests.cs': {'bytes': 14341,
                                                                                                            'gitBlob': '28fc6c9bee72d454a74d773c6cc66668ad902854',
                                                                                                            'sha256': '6714c2885562b69a5ae7a2f8b78addf4f589bba44fa5aa27b7d86ab81b080ba8'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementPurchaseOrderHeaderBindingTests.cs': {'bytes': 23057,
                                                                                                      'gitBlob': '256f096c8a40de83ff096bdd1329ba0a2443924c',
                                                                                                      'sha256': '3860df546dbbae4154e06cf08273049e6e2733ce392b36ed2aa285a7edcac9f7'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRequiredAndLiteralSourceTests.cs': {'bytes': 6346,
                                                                                                    'gitBlob': '8c909915ae7e2130bc7fc4c9148732c703e631ce',
                                                                                                    'sha256': '48accd9f3af6ccf204f7e49eb5f6aadb8f52665c94cccc48b86b9671aff443ab'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs': {'bytes': 25326,
                                                                                         'gitBlob': '13bef56d1b51a1df43fffe2e48967bd4e6f16ba2',
                                                                                         'sha256': '7a5823479455c30cac411b51cfed4ebbe247f2648e7d087167392e62be8efb20'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSourceBodyAdmissionTests.cs': {'bytes': 43609,
                                                                                               'gitBlob': '0ead4f73792f03a1f037a10e6a3ec0c32860934a',
                                                                                               'sha256': 'd8b30328a03785386c35d22635fa5a453a9944928298d4ecc5ba57af2a39fbd8'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierAddressScalarStringTests.cs': {'bytes': 15826,
                                                                                                       'gitBlob': '7bdd29d8f13395e8acd851684fb3a1137f571047',
                                                                                                       'sha256': 'deadf1da6a6500cb32bfd941682694441692abef4e34327d92b9a3c240cf2de8'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierIgnoredAddressIdTests.cs': {'bytes': 12420,
                                                                                                    'gitBlob': '2cacdd316933b7f2ae287531b185518c9720e5c0',
                                                                                                    'sha256': '7917585412bce60365fdd849f8d0b84822cf3a7e0c8c675201bf61b806fb17aa'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierIgnoredAuditTests.cs': {'bytes': 23329,
                                                                                                'gitBlob': 'e312dfb12b4522139b23033f59d74f93ca2732dc',
                                                                                                'sha256': '74ce96d1ff2879e344e52909fff7c9f819f4b32c8f76f092a524873b14eeca8c'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierIgnoredIdTests.cs': {'bytes': 12289,
                                                                                             'gitBlob': 'cfc194be743bada8ebe45f40cec97fc5a1ba6581',
                                                                                             'sha256': '61efac246ec2f0ab4752b75df55632f35b96e0e004d2f1a0fc4ec9ceff0bcf87'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierMissingParentHttpTests.cs': {'bytes': 2140,
                                                                                                     'gitBlob': '4a816860f2910ade0c0c0d7319314382d7edcc65',
                                                                                                     'sha256': '37c1f1f0712c0ac02e64614b6c78f3bea594024e4dd374cb41d7e6d873fef4a8'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierScalarStringTests.cs': {'bytes': 17306,
                                                                                                'gitBlob': '19b545ae0a96fdc1541b74cd23c75e07d79c460c',
                                                                                                'sha256': 'b3f3f0ee121ebd946509cd7e703219761c45944c56c76ab1ae40457c2a3778bb'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementSupplierTransactionBoundaryTests.cs': {'bytes': 20008,
                                                                                                       'gitBlob': 'a5ecdb83358ec34bc0230feaf008446405f4daca',
                                                                                                       'sha256': '677df3256789b43e5d54c690c5a3baf2205f5e4228b8d8356349895e54dab166'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/PurchaseOrderFileBucketWriteGuardTests.cs': {'bytes': 10702,
                                                                                                  'gitBlob': '4053059853b34e541ea0e9bfc8a4c3178e7ec4d8',
                                                                                                  'sha256': '1dd7233e3b670f7da43db431c873abeabb8c5c0e9c215c3b7ec536b142d6f429'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/PurchaseOrderFileMetadataBindingTests.cs': {'bytes': 30474,
                                                                                                 'gitBlob': '7ad16b28e7b6b0129ec1423af4eb77e1d1f9a874',
                                                                                                 'sha256': '8630c4d80e92f7839b523d9a63f8bd9c047b9543b8f771abe93445374e6b846e'},
 'Legacy.Maliev.ProcurementService.Tests/Integration/SupplierAddressParentAuditSourceHttpTests.cs': {'bytes': 8918,
                                                                                                     'gitBlob': '52aa910abfbbb7c19aa4e4cf84ac3c87e7975f00',
                                                                                                     'sha256': '1983a39bb24749a6a33c28408db529ea592e77a80fbdc08aa78ed65c20a69adc'},
 'Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj': {'bytes': 1798,
                                                                                          'gitBlob': 'af7ca6ae938ae85cac598a75852e38863fa6912a',
                                                                                          'sha256': '2cfb0dfb61be65baad2c1109954b8210b3be8b9d5648b31e5a2fcf38a5bb6d1c'},
 'Legacy.Maliev.ProcurementService.Tests/ProcurementFailureBoundaryTests.cs': {'bytes': 5867,
                                                                               'gitBlob': '174d7b6b539171ff0504930dcee5a90cb2277ea9',
                                                                               'sha256': 'db592667135263897d6e603997dc73794b1a5d52479aecd2e488c6155bee5887'},
 'Legacy.Maliev.ProcurementService.Tests/ProcurementJwtExternalizationTests.cs': {'bytes': 6374,
                                                                                  'gitBlob': '405bff44625c1e045cf5e4ae0bbd90640cf91495',
                                                                                  'sha256': 'd0f775869138188fa1a6f165981a5bac6291b37fdf232f32fa550785ac76fe4d'},
 'Legacy.Maliev.ProcurementService.Tests/PublishWorkflowPermissionContractTests.cs': {'bytes': 6315,
                                                                                      'gitBlob': '1909a03f285ceaaae0df1c4bccaa1e54f81f600a',
                                                                                      'sha256': 'b835d916d0808f566e71a63184be5fe8c608cae4a8e95d8669f14a036c12d7df'},
 'Legacy.Maliev.ProcurementService.Tests/Startup/DockerContextPrivacyTests.cs': {'bytes': 3855,
                                                                                 'gitBlob': 'd2eb962e388f53013ad8c403e7a139b8bf4c882d',
                                                                                 'sha256': '92082bea8cc22d5d6db07fc7e3f537164a6de4fcf8329a19766d8675640e3a2f'},
 'Legacy.Maliev.ProcurementService.Tests/Startup/ProcurementStartupLoggingTests.cs': {'bytes': 26159,
                                                                                      'gitBlob': 'bb88cc2a30db74a4f7cd1a972fcb2e81cf9a8218',
                                                                                      'sha256': '71c8612b5350b539f4c216d307e608673d94500032b95f159d61366ff56fa53b'},
 'Legacy.Maliev.ProcurementService.Tests/Workflows/Fixtures/reviewed-preload-auth.yml': {'bytes': 4501,
                                                                                         'gitBlob': '519acdea5d83b530c6f9a607383d80d029b7c537',
                                                                                         'sha256': '406723a08a85a06464075b55c943c86afda9a73ff1455e89b1b4c5bf116f8406'},
 'Legacy.Maliev.ProcurementService.Tests/Workflows/Fixtures/reviewed-preload-build.yml': {'bytes': 2900,
                                                                                          'gitBlob': '3c7657d9b720c63be60d5bbc88cbc2a80ab2948c',
                                                                                          'sha256': '48a3478eca18206c9184d57acd6dd32cdda196877807764d654b6f018f1b0e26'},
 'Legacy.Maliev.ProcurementService.Tests/Workflows/SupplierAddressCausalWorkflowTests.cs': {'bytes': 8463,
                                                                                            'gitBlob': '9310e8d97698f895b6c85944cd869e7d83145880',
                                                                                            'sha256': 'a7de20c862739e50d9428d2fbea5ad60cb20902a301e37c6b3088b1f8bc49165'},
 'Legacy.Maliev.ProcurementService.Tests/Workflows/WorkflowContractTests.cs': {'bytes': 54436,
                                                                               'gitBlob': '69dd38abb2b72f8b295ce1a160a68a47a2dbc89d',
                                                                               'sha256': '8ff79ccc9e5c516d493b3295cf1dfaaf5a2ddf5156cfc452e289b9a9ccf0adfd'},
 'Legacy.Maliev.ProcurementService.slnx': {'bytes': 561,
                                           'gitBlob': '48c1f4ac9b6141df5596bcdc99eb0b22b4a1213e',
                                           'sha256': 'ad38ce158871c47fc592723d0e2f144c05d2f9502d7cc90e54e8b3cc7e758074'},
 'README.md': {'bytes': 3520,
               'gitBlob': 'ca97e85e5b8e30bf8c1354695ec2aa0e5bc69f3e',
               'sha256': 'f06a47ee84adb4806a9cdb1a42dfed25eb7b28963fc9b97ffe76875d1e84e77b'},
 'ci-source/procurement-pagination/.gitattributes': {'bytes': 180,
                                                     'gitBlob': 'ee17dd044208ebbde5157ec0885f7de2dcfc2a5a',
                                                     'sha256': '25263ad5898e6581c442ba412f47368fb945a68f73838078990ab843f4bd4099'},
 'ci-source/procurement-pagination/OwnedProcurementTestContainers.cs': {'bytes': 3592,
                                                                        'gitBlob': '4697cc6bdcd412cd3e55f8fc4096f01b4e7f4b99',
                                                                        'sha256': 'bd510692924e83ec52505565af975054335b868ee039fcd59c64e3f5e30f9e99'},
 'ci-source/procurement-pagination/ProcurementResourceAssembly.cs': {'bytes': 83,
                                                                     'gitBlob': 'e43661c37bd0dff04a7bda056e28a3d3565d02b5',
                                                                     'sha256': 'ca86647f4081372cb5fedd3ee3739c12bccd5e5e7b4f097949967d04d335e61c'},
 'ci-source/procurement-pagination/README.md': {'bytes': 1542,
                                                'gitBlob': 'c46ee185a4062dae3f983d9ece4d4a91e1d20863',
                                                'sha256': '23e35bec6a2da0301f748c33cc9f0495735256035a6bbec95010b6b8f15daa77'},
 'ci-source/procurement-pagination/attribution-overlay.json': {'bytes': 1166,
                                                               'gitBlob': '7c7fee42970afb198638354df9949389ae9d1c99',
                                                               'sha256': '2be9aa4fc4b4bd2acf62d734fdac8bbe068ab2befede174d65865d8fa049e243'},
 'ci-source/procurement-pagination/attribution-postimages/ProcurementFixtureReceipt.cs': {'bytes': 3720,
                                                                                          'gitBlob': 'f0e206e2c6653b1e24749b0e03e74c80dd604336',
                                                                                          'sha256': 'f8f057f56173a9e37c509c279310f2ad9a4260e3979d4caf3375d38eddafd50e'},
 'ci-source/procurement-pagination/attribution-postimages/ProcurementIndependentContactTests.cs': {'bytes': 3531,
                                                                                                   'gitBlob': '789c1917da455c803b0821e499ee44ea64ce99b7',
                                                                                                   'sha256': '8e162be843a7914cb5c78dca203f8c933a138543867980c61e2d00568aaa6b50'},
 'ci-source/procurement-pagination/attribution-postimages/ProcurementPaginationSourceTests.cs': {'bytes': 6191,
                                                                                                 'gitBlob': '6c4595b2d3debe43e178c6eb6468a5a526a50ee1',
                                                                                                 'sha256': '9d0773ce4b017582879d916d88315ce16631c34df309822f4751adba876ab83d'},
 'ci-source/procurement-pagination/attribution-postimages/ProcurementPaginationWireContractTests.cs': {'bytes': 5792,
                                                                                                       'gitBlob': 'acbe16a92e316af793871151d60ffc152f67488e',
                                                                                                       'sha256': '1330810c804569f2e4d4794814f954a8eb487cca03578fb58834fa485b054473'},
 'ci-source/procurement-pagination/attribution-postimages/ProcurementRuntimeParityTests.cs': {'bytes': 28597,
                                                                                              'gitBlob': 'edb9d201b555f07574afcfe1dd60682bf4e6f838',
                                                                                              'sha256': 'f0d78411bdd64bb6ac75cc651b2b76470e0bc1c8ebaf6a33853bb7121eea0be0'},
 'ci-source/procurement-pagination/combined-business-manifest.json': {'bytes': 9614,
                                                                      'gitBlob': '832406fc5850da17286e39b48e592b6c0e8ee9e1',
                                                                      'sha256': 'af76f4d18ecabe559d9e0a47077febbfaf209daa4f72a772733f5a22412726a7'},
 'ci-source/procurement-pagination/compiled-roster-source-contract.json': {'bytes': 158908,
                                                                           'gitBlob': '49018e925fffeb30fd8d5afd309ed8509e8fbcef',
                                                                           'sha256': 'c84df15498aeb11a53cae5b49c43ef50b232890276dd0851eb79bae00d67408b'},
 'ci-source/procurement-pagination/consumer-source-pins.json': {'bytes': 130683,
                                                                'gitBlob': '880f3ceb1a24d741df0731deb599ab18eafb8d94',
                                                                'sha256': '8685ac5b697fc7586e877b5a87494d2aafc57634fa6ae950701aab55907cba21'},
 'ci-source/procurement-pagination/frozen-pagination70-source-packet.zip': {'bytes': 12822,
                                                                            'gitBlob': '4d79e60484c6d034fbe4c96ca8529e35eb3c3c6b',
                                                                            'sha256': 'bed0aeae59d36ac6f6eb757599c5e5b37875ff40fe73e8c9eb2a9b9f1976a17d'},
 'ci-source/procurement-pagination/injection-overlay.json': {'bytes': 855,
                                                             'gitBlob': 'c7f6d1a97f4803245059f5c9854374f3a63450b7',
                                                             'sha256': '98df7b85bf8975799d94efb1b9caa6e88670c02c1eec7abb72d8ffe0dc1fffef'},
 'ci-source/procurement-pagination/injection-postimages/ProcurementFiniteFailureInjectionTests.cs': {'bytes': 5114,
                                                                                                     'gitBlob': '0c9f3a618b3d80a6cf8a82bd58a809a9ab7509d5',
                                                                                                     'sha256': '2f86f296b3529aa5a1e28f8e0f2cf107396f3544384acdfbd9163818e9c94d8d'},
 'ci-source/procurement-pagination/injection-postimages/ProcurementFixtureReceipt.cs': {'bytes': 3931,
                                                                                        'gitBlob': '8418428f9fd9afd6790ed6ecda403acfbfbc9447',
                                                                                        'sha256': '27dd15021cca2752448ea3d86ab3c2ebab104bf3182158eaeb56eed0b3d4dd86'},
 'ci-source/procurement-pagination/injection-postimages/ProcurementQualificationFaults.cs': {'bytes': 5951,
                                                                                             'gitBlob': 'ad7e48d9966de30dd44e64cd021cc9a987b1e249',
                                                                                             'sha256': '6a1ebfed054de480eba17f7f8e1f8486624293636e60c8e6c401b5aab77a6f34'},
 'ci-source/procurement-pagination/injection-postimages/ProcurementRuntimeParityTests.cs': {'bytes': 29178,
                                                                                            'gitBlob': '2426f3e348d9b5b028b6d7346e367d21c409f0d5',
                                                                                            'sha256': 'bd36908d4389ba302731e080c56b7b27fbe8d9e9e8ff05d7371b7fb3013fe32e'},
 'ci-source/procurement-pagination/p1-controls.py': {'bytes': 15221,
                                                     'gitBlob': 'a71002163dd2b166f9a3db87c807e7a333d9ae40',
                                                     'sha256': 'd6057309fb227b1b477e850dcf85b711e9992b0f07201910e7575ac4993e1421'},
 'ci-source/procurement-pagination/primary-source-references.json': {'bytes': 365,
                                                                     'gitBlob': '71ef9512831a3a4ca5117b1ab5788d85af020751',
                                                                     'sha256': '42f4f25b29e0d13c46335c35422fffeb4127a1fafeb432d9e7379bbcb2d58e51'},
 'ci-source/procurement-pagination/procurement_consumer_association.py': {'bytes': 2864,
                                                                          'gitBlob': 'd4b9a52ef9a637681eff0dd3c1380b94a3c33791',
                                                                          'sha256': '42bf25ee9ea443787a45f2c4e5678cbe92d5bda53ca68400849ab2069049b6e9'},
 'ci-source/procurement-pagination/procurement_fixture_attribution.py': {'bytes': 7852,
                                                                         'gitBlob': 'e38a4930ea87424b99432bcd367c7edf3f7426d0',
                                                                         'sha256': 'b676e9dc3143089b73bde43b8aea98c3ff818e63434d41e57711f0c17065ce92'},
 'ci-source/procurement-pagination/procurement_hosted_binding.py': {'bytes': 4233,
                                                                    'gitBlob': '2b0f60b5792a2823b0435a4e747b6a20867a953c',
                                                                    'sha256': '04c266893ad5faf33906ee964e804a9e15eb127d6209250005b1622c9fa29b8c'},
 'ci-source/procurement-pagination/procurement_native_injections.py': {'bytes': 11214,
                                                                       'gitBlob': '6db709a0af7c8401f4f52be90db68da50e82423b',
                                                                       'sha256': '13df63423398950f751a06a2467ea3044468be2d76bb41a76cfaee749507f75f'},
 'ci-source/procurement-pagination/procurement_pagination_hosted_driver.py': {'bytes': 39917,
                                                                              'gitBlob': '75a821375780929a67428bf07c7debbff466158a',
                                                                              'sha256': 'b9514fe362e9c3a6e44b9824587179d36298b926677fd547122778514d13a3b0'},
 'ci-source/procurement-pagination/procurement_pagination_hosted_guards.py': {'bytes': 19286,
                                                                              'gitBlob': 'a159ecb4265a4130f5940a97385a3714f064f144',
                                                                              'sha256': '86ef6c8c7d1fcb8b020310fd5b47ecdd40629421d82b49ae4ecab8412ad16457'},
 'ci-source/procurement-pagination/reviewed-runtime-pins.json': {'bytes': 4102,
                                                                 'gitBlob': 'e379373cc9a74cd52d7abe6529538b9e5698bc9e',
                                                                 'sha256': 'ba4a46224cdf3074741a3070732735838c77a0ab82af5eb6489bae2b5d822060'},
 'ci-source/procurement-pagination/source-packet.zip': {'bytes': 17064,
                                                        'gitBlob': '90494701d623933f707ee56a573bf1a9f11468ad',
                                                        'sha256': 'd8748cf62c5ee7bd88b6cadbd949cb6056d4662d83e9153493328d0a95f06658'},
 'ci-source/procurement-pagination/tests/compile_source.py': {'bytes': 1311,
                                                              'gitBlob': '429d2c9eacd781757b006a5f64b654a2f62c81b7',
                                                              'sha256': 'e331c514bf950321e626b267955805c47245b81c91489e55045b7cdcc207086a'},
 'ci-source/procurement-pagination/tests/test_attribution.py': {'bytes': 12125,
                                                                'gitBlob': '481d80746cac0dfb291533b95e86a2e542b6ee58',
                                                                'sha256': 'fb908fcd9206f40161dead3959a5e187545b6738b267c3d81a5f8f6eec4ab0e3'},
 'ci-source/procurement-pagination/tests/test_binding.py': {'bytes': 6594,
                                                            'gitBlob': '4959690877076a25a9a41d5d5484901ba1a04a0b',
                                                            'sha256': 'bea6952a55f136ba7c64de9193c58cf04ae72c601e43d0fd3c75dbf5303c954e'},
 'ci-source/procurement-pagination/tests/test_command_cleanup.py': {'bytes': 13737,
                                                                    'gitBlob': 'b323ab6a7bee01879511e012c4063442b8b76007',
                                                                    'sha256': '08da8d1d74a1098c582fced1fff3588eb5994d331c129726ff64776099b0e2e6'},
 'ci-source/procurement-pagination/tests/test_injection.py': {'bytes': 9049,
                                                              'gitBlob': '3a33bff21a88e3e1cf15a38143685dc402ac520d',
                                                              'sha256': 'd935329e9bbee0550e2a59a4c04cb301498300359c92f4e6a3226cb0e58c4166'},
 'ci-source/procurement-po-header-red/Program.cs': {'bytes': 3674,
                                                    'gitBlob': '19d17888cd77004b42f290a3c0daad454dfd4b5e',
                                                    'sha256': 'afa62156da9a55476326bd9bfe1295a345f6fed72bfaaa437a5427ca93cbfef7'},
 'deploy/disabled/README.md': {'bytes': 1415,
                               'gitBlob': 'de212702aa794d005e6d31310694c8b0cb2ad494',
                               'sha256': '46c02f6ad7a694517ff040d1e15c98238f3b3369d4935df984add58cf7b1b12f'},
 'deploy/disabled/procurement-deployment.template.yaml': {'bytes': 2265,
                                                          'gitBlob': '7dbe1ee1932c2a0457aafae0eb3d0d184fd0efbb',
                                                          'sha256': '2ceec7ac2b3e365901f9cfe4e6c40d4408d9f344d5295bcc5fa78c4461c1d8f5'},
 'deploy/disabled/source-obligations.json': {'bytes': 3716,
                                             'gitBlob': 'a03b6ce18073a9cdd23d4fb7c67761005f5cbfb0',
                                             'sha256': '05b7a902850b31c448d35927b3839edcefd41270c4dbc7f5d8b65ffe2c25e61e'},
 'docs/Invoke-StartupArtifactProof.ps1': {'bytes': 6698,
                                          'gitBlob': '09a0611d4dc205b4e5f6b1322b7e855641c032c1',
                                          'sha256': 'd2841ee7208187d1e0d4605ebb49c4091c6a34f3887ed9f4d4fd0a9cfbbd1f0a'},
 'docs/design-artifacts/issue27-procurement-runtime-parity-red.cs.txt': {'bytes': 24006,
                                                                         'gitBlob': '1b6408bf653d4b116fe2d06bff8d45f0c23d3975',
                                                                         'sha256': 'ade96c73725baee64d838a4f35a0f511d1fa1e7db9972485902840caf5cbd91b'},
 'docs/migration/source-72eb9f1-purchase-order-header.json': {'bytes': 3982,
                                                              'gitBlob': '6ee7ab7c28fc6bed1100420f3967e445631a7860',
                                                              'sha256': '7ed297b7ef9a43e5f1cd60317acb5c8799f45839f33d8fa9d7d337291af5a4e7'},
 'docs/procurement-actual-auth-program-join-20261005.md': {'bytes': 3350,
                                                           'gitBlob': '7884299252f687c333ec3d14b7884c1d97e4a999',
                                                           'sha256': '7ea0fb6cb7a550e4a055c123c2edc58c393d710bc6a738de5db4d82c24157b52'},
 'docs/procurement-address-acceptance-20261003.md': {'bytes': 5362,
                                                     'gitBlob': '5cadca4ef777c4986adf6df6c3e974c6f893ac6c',
                                                     'sha256': '07fa4870b5f68f93a5ebd7ad338b24e2cb34b3618a005786859befdc2a225fd8'},
 'docs/procurement-authenticated-iam-20261005.md': {'bytes': 3049,
                                                    'gitBlob': '0fc0457ebe539d962653be7aa4de0ae43a628a63',
                                                    'sha256': '8ff238ac159260d8129c52aac410e23efbabada203d8ace450bdfb5ddf406ec9'},
 'docs/procurement-durable-create-design-20261001.md': {'bytes': 27423,
                                                        'gitBlob': '0bb7f0a5486cd8dfef474807df944af8a7ff56af',
                                                        'sha256': '79de2779a248d54e3e6dc6b26c8d9171db458f6d5e528e2692e10387aaa38fb6'},
 'docs/procurement-file-bucket-source-boundary-20261022.md': {'bytes': 5832,
                                                              'gitBlob': '389d8aba5a17755582926bc408341e4c4c9af94e',
                                                              'sha256': '8c14b35184caf29163568b25532a7d5425c432a91d0fc5ee88a1d17dba6725b8'},
 'docs/procurement-file-metadata-binding-contract.json': {'bytes': 53984,
                                                          'gitBlob': '2b690093dee9cad38773abc1009559f2eae45c18',
                                                          'sha256': 'd7decd4e79a5d0b590c466a779b9983971a224c8467e16f3ed31a7b5f2559c94'},
 'docs/procurement-focused-lifecycle-contract.json': {'bytes': 3674,
                                                      'gitBlob': 'efd1eee081b4b917330e4b8e8d176bf11156f23c',
                                                      'sha256': 'ce64e22696dad11ad706dba71b5da38ecfa8ebf6459e418f39d7a3f606574e78'},
 'docs/procurement-focused-workflow-contract.json': {'bytes': 8901,
                                                     'gitBlob': '5e2952e22083adb18d633b5e2e8a781bff3f5936',
                                                     'sha256': '9be8fd79d5f47fee695dd9ae26f2d6b5953b9cf1cd2cb4ca135aa3ed7de2e697'},
 'docs/procurement-header-ignored-fields-contract.json': {'bytes': 190807,
                                                          'gitBlob': 'cf3bbcddbe1001a042219456e07d15b675bb3365',
                                                          'sha256': '86d8561f37ba2347913608d6d59dc05ab148d8293814dcd420b2220d62744e2a'},
 'docs/procurement-master-query-contract.json': {'bytes': 1618,
                                                 'gitBlob': '0ce9f584afe54aede2da16ed10f10499a56138e0',
                                                 'sha256': '7bb47844212fb9e4318bd5d4b771facd3ab82e46074329cb798094fd06071d6a'},
 'docs/procurement-master-query-source-20261005.md': {'bytes': 2158,
                                                      'gitBlob': '04d6454d9dd4681da0677b0d38d5c02078495458',
                                                      'sha256': 'a7e0214c634fbbfcf57bb5eaa8e1d1f8cc7c4fcf880845da0e0176197314e043'},
 'docs/procurement-metadata-identity-contract.json': {'bytes': 115199,
                                                      'gitBlob': 'd984e8cdf2deefea3740077c012a2b865616d581',
                                                      'sha256': 'deee21c47b514702f4fc6becaec34fb1e45d15b1e592fd355e36fedab32c71ed'},
 'docs/procurement-metadata-ignored-audits-contract.json': {'bytes': 228634,
                                                            'gitBlob': 'e4ab24537a3ff28477c66d3adac52ba7ea311184',
                                                            'sha256': '062583576f82b6b2fcf034ad8514f24954765366e3dfe0329754f77ddfbfbeda'},
 'docs/procurement-object-name-source.md': {'bytes': 2048,
                                            'gitBlob': '55ee559c907b217ed364e52649d645be85a2c224',
                                            'sha256': '2cf9acda683fd526c2198770f1f9666c580bdcc823fc6a22ec6b42d50f26e90b'},
 'docs/procurement-po-header-hosted-red-contract.json': {'bytes': 32735,
                                                         'gitBlob': '621c3246cfba8c98638946ed913a234d1dcdeb38',
                                                         'sha256': '1ebfa3c05ea2ef9e029b45b079efbcbd3a7a70bd3830a251c08eb10086bbc3b0'},
 'docs/procurement-publisher-validation-20261001.md': {'bytes': 6272,
                                                       'gitBlob': 'c505c1a4b8844875ea059278ffbe08b526034d09',
                                                       'sha256': 'f88f1e029d46144191cf95641a7416394ac48191d60a721edf3a4eedf3aa4c4a'},
 'docs/procurement-runtime-parity-design-20261001.md': {'bytes': 35230,
                                                        'gitBlob': '26c881a524a67e43c9b7a879b8442b931ff6b2fb',
                                                        'sha256': '384ae5842c363606794420ef8cd787691f4deb3a318bd8cac4e9811c0d5e309d'},
 'docs/procurement-supplier-address-causal-contract.json': {'bytes': 14456,
                                                            'gitBlob': '44292d7ad1e23694ba34364dc7be8799e559bd13',
                                                            'sha256': 'fbd33b31b8ec68a95a4f50dd0b70986403b377bfcbb5146ec8dd3c9043b17bfe'},
 'docs/procurement-supplier-identity-contract.json': {'bytes': 72559,
                                                      'gitBlob': '951169829c8612c49f7f5c6f47aa70f8a2761cf6',
                                                      'sha256': 'a2b172a240017dd6df98de03dd31adb349a3f361ae0b48eec6fab34613fdc409'},
 'docs/procurement-supplier-ignored-audits-contract.json': {'bytes': 108947,
                                                            'gitBlob': '06919b220169d4dc38a06b969e98f00011d734b3',
                                                            'sha256': 'a96e51a4fbc230dfa3b04de66612b8933d17ed17d514488d4f470b1a36827a06'},
 'docs/startup-context-source-parity.md': {'bytes': 6470,
                                           'gitBlob': 'f99576f73b695b98a5c43c4e4fd5f998347a3d36',
                                           'sha256': '0e8f8300a16cd15536e5f3bb082a7c807d25162ec0aec58b8b70a03e42e76382'},
 'docs/supplier-address-parent-audit-source-20261023.md': {'bytes': 10553,
                                                           'gitBlob': 'fec8cba2b5856efbdf41ffc03597b70956076a8d',
                                                           'sha256': 'ff99569027156f376d67cc12f3adea4e5c27706cb46495cb388921a038f20c6e'},
 'docs/supplier-mutation-original-boundaries-20261022.md': {'bytes': 5355,
                                                            'gitBlob': 'ba68a35daed7ddc23496d680ff893593c0503a61',
                                                            'sha256': 'aa6d7a0b93821d37526726840ceda045db1d6c16bee8250e66d0599a6e84a9f4'},
 'eng/commerce-source-intake/README.md': {'bytes': 2227,
                                          'gitBlob': 'a04580ca9cb02b6e70b85d9be695d70b65702263',
                                          'sha256': '30f998197a08ea1e03132275bb286075ecec3c30e9794bc744ec857ab1d41bc8'},
 'eng/commerce-source-intake/capsule.zip': {'bytes': 423218,
                                            'gitBlob': 'a4354aceccc65c09f5f1f09313fe2dcdf0d56e94',
                                            'sha256': '7d824256f061dae0e5890b475419862c18d328dfe70fe92a64fbfad7cd150c9e'},
 'eng/commerce-source-intake/commerce_lane_policy.py': {'bytes': 236,
                                                        'gitBlob': 'b5d43db8b7f25b491358b5073a2cca58d46cb7ae',
                                                        'sha256': 'a4e25570c10eb5abd3d2a361c023a76870a5638c12a6331795c63db7008cfd6a'},
 'eng/commerce-source-intake/commerce_source_adapter_v1.py': {'bytes': 7476,
                                                              'gitBlob': 'dbbfcc998a9773e2b0487019d43394e75496a528',
                                                              'sha256': '9ddd09bd120d1f79bd4b4581cd3e4bbcc52e0216fe8a632619e25e7bf6e81e15'},
 'eng/commerce-source-intake/policy.json': {'bytes': 135346,
                                            'gitBlob': '9c5db39977ad82d8345651145f85f8b93babf6de',
                                            'sha256': 'b85e966fa74cfa5aa022fc502f56038d9105d3dece17612196dbdd6a89d8258c'},
 'eng/commerce-source-intake/provenance.json': {'bytes': 1063,
                                                'gitBlob': 'ad7a0a839c0a23ae453cb3a861d1478221f18144',
                                                'sha256': 'a28b3db07c7b6c2058a9be58c4b1a8d26252db616e0ab7e95429e7222eb84749'},
 'eng/commerce-source-intake/run_commerce_source_intake_v1.py': {'bytes': 5397,
                                                                 'gitBlob': '5628fef5f29bf4040a81cab091e174eb2c6263ff',
                                                                 'sha256': 'e58c74b9f092b10a30ffa4b30b998041ea5e68e677bfc973f79530812171e349'},
 'eng/commerce-source-intake/sealed_source_capsule.py': {'bytes': 12296,
                                                         'gitBlob': 'cab6997ff2af48bdd4ac7e9240cd12d01e5b3190',
                                                         'sha256': '44a8a5accac9da11422d606be02fe28487642215df511b5f1c4284296a453ee2'},
 'eng/commerce-source-intake/test_commerce_source_adapter_v1.py': {'bytes': 7679,
                                                                   'gitBlob': '5401b7b6ba7c262aa7640cc872ac7264037b6068',
                                                                   'sha256': 'a797fa07e8e84fc8299fee584da8792f1f0edde2490a240557b66cd2a0c11b6e'},
 'eng/commerce-source-intake/test_commerce_transport_entrypoint_v1.py': {'bytes': 9946,
                                                                         'gitBlob': 'd17469897f09ad7e64aa06aa0fc1e1fd6cbc7a00',
                                                                         'sha256': '8cea286be6b07c28c9a7d71198a4e23d463ab1fc8111a4f4ae7a30c4b2870fda'},
 'nuget.config': {'bytes': 197,
                  'gitBlob': '765346e5343d46ac83654843869dc06b65b2bdc4',
                  'sha256': 'aec93b5637ab6d62470979a008990a4a336a287ab83a3f2541849ae735674055'},
 'scripts/Render-DormantLegacyProcurementDeployment.ps1': {'bytes': 1853,
                                                           'gitBlob': 'ce5eaa9fbdc5bdd0bbf88fbce8af572331b9a594',
                                                           'sha256': 'cd72bf4686d71a19d5e08903a57b622a2eb7ab7ee3ffd3a6021914e37eb82aba'},
 'scripts/observe-file-metadata-providers.py': {'bytes': 15472,
                                                'gitBlob': 'caa40a34242f259cf0582cc5374c9edb0416d78d',
                                                'sha256': '1f87b33d5a0c1d9af6b9d1f16998922bc24c47f8e8187968ee33017a9fa4fa80'},
 'scripts/observe-header-ignored-fields-providers.py': {'bytes': 15496,
                                                        'gitBlob': '9e3ce41ef9d13090b0b38dc694b8c03b557c51e9',
                                                        'sha256': '9e31c31416f3d3822ab399913f7c34e4a4f682eaf406d6f0b41757f406ba66d6'},
 'scripts/observe-metadata-identity-providers.py': {'bytes': 15493,
                                                    'gitBlob': 'bdd2544a6ff844d6500512db9ac255192def30fb',
                                                    'sha256': '41d66243db55e9efa80d42a200c6f444512af3bb1da266cb2353cd3a9d9cf17d'},
 'scripts/observe-metadata-ignored-audits-providers.py': {'bytes': 15506,
                                                          'gitBlob': 'c187747f8d602bb015602e4acfbf8bab80a03b37',
                                                          'sha256': 'abe1b682f6e2103449c7b0e3ae749d7ac0f20d2bbf97c7c9965f5f83ff75ad21'},
 'scripts/observe-supplier-address-providers.py': {'bytes': 14162,
                                                   'gitBlob': 'f3a81f3214e59c52c53a2d8f5e2808285988ca75',
                                                   'sha256': '1f76d46e26d8553598f01fff7d7f4bc95ce42febd56125beea2524233d411063'},
 'scripts/observe-supplier-identity-providers.py': {'bytes': 15535,
                                                    'gitBlob': '15b7a3e27e6e468f1f490ffb019eaede8f7239c6',
                                                    'sha256': '849ba7ce84b0475f18636e18cb7d0cfc788201a0ef0b8e4c03b0b3e54fc1a515'},
 'scripts/observe-supplier-ignored-audits-providers.py': {'bytes': 15503,
                                                          'gitBlob': 'd35a08ddc313367c2a549ec770bb42127f209698',
                                                          'sha256': 'db5c6f96a2195af0be220b676747d8e3b05a014ead3a48ae3e216c5019ae3dc3'},
 'scripts/prepare-file-metadata-baseline.py': {'bytes': 13802,
                                               'gitBlob': '56f24eb9163a284a81b1a9d21b6a29f2f00adb6d',
                                               'sha256': '2776de9decd37817db4de088f5fb617762ad26f9114d4a9c934edb285f2f36f0'},
 'scripts/prepare-header-ignored-fields-baseline.py': {'bytes': 29390,
                                                       'gitBlob': '9837224e836dff6b6a8ee2d3ba2e4ca49f6ec873',
                                                       'sha256': 'e9c5f5a94e6555e055907187bbc792ade61c0f863441b1b798a0c8c6f2d82d82'},
 'scripts/prepare-metadata-identity-baseline.py': {'bytes': 26675,
                                                   'gitBlob': 'a3b423eaeee22bb5ba8893ef90b96b4cf08573f1',
                                                   'sha256': '35285329daf1a2b877b3ef51c68a5de04648cc0e02174fb647e8909547f53f2f'},
 'scripts/prepare-metadata-ignored-audits-baseline.py': {'bytes': 27437,
                                                         'gitBlob': '4f1e2f7fb8c8767ef79b612320d78dee20674d70',
                                                         'sha256': '783ef496eca1ac96bc440b77d26ac797a3f4b6f32bc4cece834d2815b9f96381'},
 'scripts/prepare-supplier-address-causal-baseline.py': {'bytes': 4223,
                                                         'gitBlob': 'dfd512b988182b2126a18a7d273bd88e56473a03',
                                                         'sha256': '379cb1ebd190db7169704d912dfa805870b590f23211a7ee917960f7efaa31f5'},
 'scripts/prepare-supplier-identity-baseline.py': {'bytes': 14624,
                                                   'gitBlob': 'b51d15c92ac269c86d2c24a0a601343f57364d2d',
                                                   'sha256': '174b6ae240b2382479dc748264f89294b1b755bd9d334fda17097419cd6bbe99'},
 'scripts/prepare-supplier-ignored-audits-baseline.py': {'bytes': 28202,
                                                         'gitBlob': 'f5413a775d9fba84812d60533391e2d74bf599b7',
                                                         'sha256': '9e06de12b2d0c995a57f1a081b3c21fc3bf8c08059a76e5557c0c671a550e7cf'},
 'scripts/procurement_address_null_consumer.py': {'bytes': 12667,
                                                  'gitBlob': '170bc6d1d77be35fdbe86845b7c5686279df32cf',
                                                  'sha256': 'fbbcf9a4c028059c6636cd6b3087216552d51e19a2cdb2f7179bddd924ea0062'},
 'scripts/procurement_artifact_transport_consumer.py': {'bytes': 6099,
                                                        'gitBlob': '7b0152fa302b565e3c1dee6f6e9a72f30ef109c5',
                                                        'sha256': '646eeebe5df97543e6891d8453b15e9520bcde3e865baa66a4584a1f5c97bac7'},
 'scripts/require-metadata-identity-admission.py': {'bytes': 3583,
                                                    'gitBlob': '0c91e5b94fa2ddaeb5e602ebfa68e242efd81a7a',
                                                    'sha256': '0dbb7c4e4fac249912b58f54876a9a341216beac495a14f1a75b325ffe7d4f9e'},
 'scripts/supplier_address_owned_processes.py': {'bytes': 7949,
                                                 'gitBlob': 'd96fdb5bf589c7aef97ca8136b20e28f29669bd4',
                                                 'sha256': 'e50fc5257431d13279e950d805816c2472704af0f1b39045475f1310a0065deb'},
 'scripts/test_file_metadata_binding_results.py': {'bytes': 37183,
                                                   'gitBlob': '93d47d4fe880add749a36de5376be1f10f540991',
                                                   'sha256': '3b2ca20eb125affbe8131d06f270562dd6e8ceeb1463a156a70e186522ee331f'},
 'scripts/test_focused_workflow_results.py': {'bytes': 12649,
                                              'gitBlob': '83e45737d20ae821d6d3e57cce80d0b863431cba',
                                              'sha256': 'f852b3fd701ebf6df9fb0dcb67efb99b6b920dbaede94e37a0957bf198465679'},
 'scripts/test_header_ignored_fields_results.py': {'bytes': 45772,
                                                   'gitBlob': 'e5483b80062a9ba7d222b096d92612415f4f23bc',
                                                   'sha256': 'ca0cce544c4ca25c0275a9aa0d400e7546cb39efe1ebe451014c94de034b64ea'},
 'scripts/test_metadata_identity_results.py': {'bytes': 47347,
                                               'gitBlob': '6d12f0c79633411dfa815fd0feb5741042e752d6',
                                               'sha256': '9e0862c6a4cb3d7c5960c89281bd7955f99554e271934ae75f2589b186593864'},
 'scripts/test_metadata_ignored_audits_results.py': {'bytes': 46008,
                                                     'gitBlob': '3e7beb6aecb6df0ec20d9a37a6d7037310f8f697',
                                                     'sha256': '31866f1b45dfff003028780800e28fadd6b648546334498dd41dc79986179e22'},
 'scripts/test_po_header_hosted_red.py': {'bytes': 39025,
                                          'gitBlob': '67504b5e4727de73d13044b15262b7e8ddcb17f5',
                                          'sha256': '60c9dab1a3fa6b310281221d9bc625e37859e8c0cfaf38491af1a09aaf2259d4'},
 'scripts/test_procurement_address_null_consumer.py': {'bytes': 20646,
                                                       'gitBlob': '6069d40cedf4b4f46d2bc29adcc3bad0c867b120',
                                                       'sha256': '34f0a4923f8dbcee49638b07f737b32c4e9fcbb5c762570332b74648cc48a689'},
 'scripts/test_procurement_artifact_transport_consumer.py': {'bytes': 4233,
                                                             'gitBlob': 'f31d246ebe95b6ef82035c3b479068a0188ba0bb',
                                                             'sha256': '58f7d1b5d144ed760947da987bf6cb84a5e05861c7bd1eb417d4b225231be9dc'},
 'scripts/test_procurement_auth_program_inputs.py': {'bytes': 25546,
                                                     'gitBlob': '9fed6097fc3bf9214cb07589f32668cad92e5746',
                                                     'sha256': 'e6c1f1fa17fb64139ca2685faacedc1236e16db3545df29243b1ce032c2f7a41'},
 'scripts/test_procurement_health_aliases.py': {'bytes': 7240,
                                                'gitBlob': '72dc1c4eef107cedfdc03c1c3bb9d5cc560c2b44',
                                                'sha256': '1f2d39936fefec0f50a8f512ab3004cd9173978badc9028048981774f94f402d'},
 'scripts/test_procurement_string_boundaries.py': {'bytes': 10562,
                                                   'gitBlob': '0eb2b71c1aa56bc742500eba0b51b7935e3bf810',
                                                   'sha256': '1cc296372f08738d39dc58815a0418684e2d0afdef3bc6e6b662f0980e7a7fbd'},
 'scripts/test_query_fixture_encoding.py': {'bytes': 1128,
                                            'gitBlob': 'c431b368af34dd2f1c7c3b966825b2e68c0808ab',
                                            'sha256': 'b934418cab8122a52165d0f3eca4d13f0028de687ea2c7472b57c6fa28e79931'},
 'scripts/test_supplier_address_causal_results.py': {'bytes': 21957,
                                                     'gitBlob': 'd30992eccec81d3214d61371c9d8e3ff8c97c1e2',
                                                     'sha256': '7473edeee54f382b44765c428743309898df3882f958a67c559300189cc45f28'},
 'scripts/test_supplier_address_provider_observation.py': {'bytes': 24109,
                                                           'gitBlob': 'c78d8e8dc5d8e000d26eeebeb2966b9ebcf9286b',
                                                           'sha256': '7027f4c4c7857a004d55b2e446cc8be38843c86583acbfba02b36c1372081282'},
 'scripts/test_supplier_identity_results.py': {'bytes': 31934,
                                               'gitBlob': 'da10ba96f75b89c14ab43eeef78d5a687597fd47',
                                               'sha256': '67f70c9a089cea19bc46437b92e5adabeffd2bb6cbb87f8c5925b9774daf0e6c'},
 'scripts/test_supplier_ignored_audits_results.py': {'bytes': 45818,
                                                     'gitBlob': 'bc864396d9da3c8d074618b7280f347ea6755932',
                                                     'sha256': '7aa5d0256f7adbf8e61fb013b6c658f6418dd313115e0d25e471c9683e34fc52'},
 'scripts/test_supplier_parent_audit_consumer.py': {'bytes': 5380,
                                                    'gitBlob': 'adab41322af29c140e82923e335d0a6399abbb1c',
                                                    'sha256': 'cfe4f5387898b0f509f851f9d6cbf7599e0f89a8fead30da97fd78a7c44607a1'},
 'scripts/test_supplier_parent_audit_harness_consumer.py': {'bytes': 7630,
                                                            'gitBlob': '40db8787cd5f6d24b726814aef5967a8c047cd1b',
                                                            'sha256': '7179a781782f468deaf336d71478dc6755775b6cfcac8ba77a6a7b225c7991e8'},
 'scripts/tests/test_dormant_deployment.py': {'bytes': 6982,
                                              'gitBlob': '899e3d3a833acfd0aef475a57f23fcf1938e3f2e',
                                              'sha256': '59c90d3361dfcb67a7e0f591092ef605aab94492e73c10ca0bc80f3e38f6ca44'},
 'scripts/verify-file-metadata-binding-results.py': {'bytes': 11631,
                                                     'gitBlob': 'bc189f226d5038f9729b1c8f0827ceacd440238f',
                                                     'sha256': '0b7d46e175101a962f9d93cc10de57941d6d8647920dbe6087eab58fb96e1773'},
 'scripts/verify-focused-lifecycle-results.py': {'bytes': 2009,
                                                 'gitBlob': '566101c201cd67931f76ef77eb94d86430473c88',
                                                 'sha256': 'f07e76f274e205c7626b78573bae0252e4d33966c33cc1d2080c2f9da0ce47dd'},
 'scripts/verify-focused-workflow-results.py': {'bytes': 5775,
                                                'gitBlob': '4ee7a1337d00fb8db29ca20af80911cd48460335',
                                                'sha256': '7e4aadc17a6fa4b48eee9cf39ea7c5c8edf55fbb11746f7db74d74bc40b9b819'},
 'scripts/verify-header-ignored-fields-results.py': {'bytes': 13571,
                                                     'gitBlob': '009579c8ec2790bd0d0338a4fd61cb083cfdbcd6',
                                                     'sha256': '8b864d1b74f500e4f64e267a533fcae775389485cb22731d1e42a8557f014b3b'},
 'scripts/verify-master-query-results.py': {'bytes': 1982,
                                            'gitBlob': '30d09e32ecabf41e0b6b57755a716af63b908867',
                                            'sha256': '0692ff2e35d45b8215c908fafb2fb8dc3867f084ac0ea3f2bab8ffdaf074c7fe'},
 'scripts/verify-metadata-identity-results.py': {'bytes': 13481,
                                                 'gitBlob': 'a1cb8d97044e6c4aa9da33549e967551074b616d',
                                                 'sha256': '5a54a6b559b2147cf48aa8d5a94f68c6864f317685909f769e7f57607a4d0a95'},
 'scripts/verify-metadata-ignored-audits-results.py': {'bytes': 13230,
                                                       'gitBlob': 'ffb85569c189055a9fb8a2ae66aaa8cd6d3c8005',
                                                       'sha256': '4b8c6360978d077eab829471e08578b4658c464d19f6eea52a2a64a5323701d3'},
 'scripts/verify-po-header-hosted-red.py': {'bytes': 33646,
                                            'gitBlob': '12c5f6affdf4eab174795b83d86daf7cdae07cd4',
                                            'sha256': 'b172876c2fb67c3142d20a7110beaca4ad1e4042b1abdd15921e4cbb59bc282b'},
 'scripts/verify-procurement-auth-program.py': {'bytes': 47226,
                                                'gitBlob': '1e5cb24cda948f01e16f9a7596fc0a426b601d21',
                                                'sha256': 'd472387f802ee02c8f8adefb8fa7add0ffa46912c97a1e6ea280a5e465f8a167'},
 'scripts/verify-procurement-defaults-deadline.py': {'bytes': 2649,
                                                     'gitBlob': '6d1c14c390db0fab67b7774834270d41fa5a8722',
                                                     'sha256': '9805f3e1ccddbcce2f941b2ac1bc8a8f5b69820d87ac374fc180344d56a2b3db'},
 'scripts/verify-procurement-health-aliases.py': {'bytes': 8446,
                                                  'gitBlob': '08e2b6ca6a0dfc00408ae0dccbd11565a051e218',
                                                  'sha256': '7b2249f1050022aa9b5059dab5bdc4bdad9a4d9d0984a7e3b301ae422497ffa5'},
 'scripts/verify-procurement-literal-boundaries.py': {'bytes': 7876,
                                                      'gitBlob': '46717e5dccd07829ab719a599f256053a5bccc48',
                                                      'sha256': 'c0ec211934f613dc5a5d9f23ff1672650281c80028e5a118f946438e916ac396'},
 'scripts/verify-procurement-nullable-sorts.py': {'bytes': 2837,
                                                  'gitBlob': '5ad589f506aa2b010b35367431b95ef437d67c77',
                                                  'sha256': '4d8adabefd898d6c9eb88dbec0e08ee75da855a713e63c6f3ce3779e38e9aeff'},
 'scripts/verify-procurement-string-boundaries.py': {'bytes': 11049,
                                                     'gitBlob': '891db41d6288a77092aeb9b5590e524a2576f72e',
                                                     'sha256': '767b3c28e8544a8cae9940c4aff8b4b7377f70307b6ff31d6c7658c7d2f46f6b'},
 'scripts/verify-purchase-order-header-results.py': {'bytes': 19980,
                                                     'gitBlob': 'f4e1656678e823c181aa162570e9edb15cb95b82',
                                                     'sha256': '10f6ebb7932a65312842cc8a2aaf95b5d844ea662a8a2a6b26694ebc2d992a8e'},
 'scripts/verify-query-fixture-encoding.py': {'bytes': 1070,
                                              'gitBlob': '5cca199ed405aeb9c777fabf8aba6374abc4b7a6',
                                              'sha256': '40a6ab32450c32c2bddcab1a178ebd668cc91319117934c13f52970206a6abb5'},
 'scripts/verify-runner-coverage.py': {'bytes': 2085,
                                       'gitBlob': '17a518e5ab57caa59b4a5f54349f8c0e6b179e58',
                                       'sha256': 'ad67dd8f9cb3654e388dd07c3cba8b2644ac0c3f8ceac2c2fcfd172d5b0cec93'},
 'scripts/verify-supplier-address-causal-results.py': {'bytes': 9708,
                                                       'gitBlob': '4b077751ebf9e61de97ee16dc1c57216598e59c7',
                                                       'sha256': '214ce6f030948793d1401f3b4b62f7801883ea3514b7e1ce0f4e7c0130d4c45b'},
 'scripts/verify-supplier-identity-results.py': {'bytes': 13074,
                                                 'gitBlob': 'bbadbca13c01738aa29c4fcb92d8d62eba2e19d7',
                                                 'sha256': 'd85e60eb1dcd236ba476e9d99d097e323e04b4cec363c7cf87c111ffee5922be'},
 'scripts/verify-supplier-ignored-audits-results.py': {'bytes': 13227,
                                                       'gitBlob': '2b718a0b66baeab9ee321f23482df27addabd9f3',
                                                       'sha256': 'f3141468b8b0dd7dc557c24a144d5cb5ea834d2916f4a0edf973513b1f9ab023'},
 'tools/ProcurementAuthProgram.Tests/AuthProgramProcurementJoinTests.cs': {'bytes': 22800,
                                                                           'gitBlob': 'b3af05f512e481e0807bc5c841d3432b0ba87c08',
                                                                           'sha256': 'cb30837c832247aaf1be11518a2e4c435c42cdbb276ec1a14af060f32d8a955f'},
 'tools/ProcurementAuthProgram.Tests/OwnedCleanup.cs': {'bytes': 1966,
                                                        'gitBlob': 'faeb6bc3057ea29a1f9df408ee0eef06d19e86fa',
                                                        'sha256': '5c1a9419c88c9274ba30835353d2400e0d6830464793d12698c8cdd48645a133'},
 'tools/ProcurementAuthProgram.Tests/Procurement.AuthProgram.Tests.csproj': {'bytes': 1274,
                                                                             'gitBlob': '94a238353a17cbc811af5cf8afdadbea26587ab6',
                                                                             'sha256': 'e6f812938471665dee5d238c59dac30a1005a5a64b43f01b6b4deb8701bf9327'},
 'tools/ProcurementAuthProgram.Tests/public-graph-accepted-9c801.json': {'bytes': 1940,
                                                                         'gitBlob': 'a7682b53f717748c36898f252ada11a74f5331b3',
                                                                         'sha256': '6ea6cb5c92569c2134aa348e6756ffdd55612f1e9fea162886d7232bf585031a'},
 'tools/ProcurementAuthProgram.Tests/public-graph-address-country-id.json': {'bytes': 124119,
                                                                             'gitBlob': 'e433e128dac8a930b2e8b01f9639ec92f848aa4d',
                                                                             'sha256': '4a7deb0c024900377795e20f2b0521cffd0f045913dfbf1f97e05a1bf966e9f3'},
 'tools/ProcurementAuthProgram.Tests/public-graph-child-replay.json': {'bytes': 19184,
                                                                       'gitBlob': '3105f75f8da062c3b3d903aece003593f6997b72',
                                                                       'sha256': 'd4aab5b24027fb666b8571c67450c59cd6b188970b34818fa308b34e215edd1a'},
 'tools/ProcurementAuthProgram.Tests/public-graph-file-bucket.json': {'bytes': 16939,
                                                                      'gitBlob': 'd18e8360b1719e325695577151b33ba2ec968ad9',
                                                                      'sha256': 'd5890949f9f397c16fc3ca225993946f9abf8efef866c20e82653210724884a8'},
 'tools/ProcurementAuthProgram.Tests/public-graph-file-metadata-binding.json': {'bytes': 32086,
                                                                                'gitBlob': '09a9173a32edeef0d372c44b4ae8f0eb99e444c0',
                                                                                'sha256': '47c06849201f62ac58d01da3043eebe0e07a2b6ba64b20c586fee882d3dee1dd'},
 'tools/ProcurementAuthProgram.Tests/public-graph-header-contact-ignored-fields.json': {'bytes': 84831,
                                                                                        'gitBlob': '8abb62f1d27efba94f2b54395e3bbda77a9a786e',
                                                                                        'sha256': '53ab8da5c591279c47233bf1e1c6ce26f90fa2e28f2744b81148bd20c632c90d'},
 'tools/ProcurementAuthProgram.Tests/public-graph-header-ignored-fields.json': {'bytes': 71711,
                                                                                'gitBlob': '185048d4d5f6613bcb993faf1b9cf77f23ba25ec',
                                                                                'sha256': '92f6292a914805ef7a5895578cae2da6af2af4f8adcef69075a5b65982a009be'},
 'tools/ProcurementAuthProgram.Tests/public-graph-metadata-ignored-audits.json': {'bytes': 110978,
                                                                                  'gitBlob': '8bec326c5639c6c437abbb3926bf2000bd3ddd8e',
                                                                                  'sha256': '3ca45a0827fea6653f6fd0e4d3966f363bb013e418fe20e627c82016d0fd6f97'},
 'tools/ProcurementAuthProgram.Tests/public-graph-metadata-ignored-identity.json': {'bytes': 58812,
                                                                                    'gitBlob': 'd5ec8073e418e461e61e0fffc5dda47318b95861',
                                                                                    'sha256': '3ebc8ce7a0a5ba574a59ce17d7d0799886eecb02ce4c59dae9f8d74b671d2f2e'},
 'tools/ProcurementAuthProgram.Tests/public-graph-purchase-order-address.json': {'bytes': 19491,
                                                                                 'gitBlob': 'e8343a3795e715632a9d5856b9b2f5080066e20a',
                                                                                 'sha256': '9a4334ef83b14ac2e20fca23599ad2e86cbcacdb2e216d2bf40420b37c96c97f'},
 'tools/ProcurementAuthProgram.Tests/public-graph-source-body-input.json': {'bytes': 138331,
                                                                            'gitBlob': '0a3573be3d7fa1d08a6071b71ed54449c9a3c578',
                                                                            'sha256': '65f61c83ca0f2eeb653bf7fdf85fefeb22c85552b44f49aec68fce4c1db24192'},
 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-address.json': {'bytes': 16635,
                                                                           'gitBlob': '087837bd5777bc41880f512ffbafb8815dd4c863',
                                                                           'sha256': '15aefdb6d7d587b3ca9c6c9183f732dc85ab8df0974a8b6ab1f416f7adc73177'},
 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-ignored-audits.json': {'bytes': 97827,
                                                                                  'gitBlob': '45dd7bd104ef039c58eed5ce19b7ef81de2b9e20',
                                                                                  'sha256': 'a97f8ef186e665d0e9610fcdbfc566172bc7038f6d7b82897ddfa21b52798057'},
 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-ignored-identity.json': {'bytes': 45305,
                                                                                    'gitBlob': 'dd16549fda20264df88d58ea201ba8cad98c0daf',
                                                                                    'sha256': 'af852115e36d3c8bc9f2b4b38f3b5287cd85aaeaaa8f6bc8b52bb4393c72793b'},
 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-omitted-size.json': {'bytes': 152746,
                                                                                'gitBlob': '167399ff7acfd9e298a257f9f856090f9b3d1b3d',
                                                                                'sha256': '97363e10747b4c3ad5d84c1da6a4456190388ab1d09f831f713e822f2a115d78'},
 'tools/ProcurementAuthProgram.Tests/public-graph.json': {'bytes': 13061,
                                                          'gitBlob': '7cf8f0207bf5fc3bee37b67f61762359550c7c7b',
                                                          'sha256': '205063c79697948343ba659b13757b68ef4814d1b62861484a1dd90c0b8e7d41'}}
ARCHIVES = {'Directory.Build.props': {'archive': 'scripts/dependency-predecessors/main-ebf-00.bin',
                           'bytes': 515,
                           'gitBlob': 'b47c8d23651f11ea8366bb63f4520fb8de6c6df3',
                           'sha256': 'b03b93e505f9bd0f5d396c5041d9b35d6cfccb454384ba8151e55e05edf45083'},
 'Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj': {'archive': 'scripts/dependency-predecessors/main-ebf-01.bin',
                                                                                      'bytes': 1572,
                                                                                      'gitBlob': '30c131eb10c554b445e878c0b148cbe79d8c7cd3',
                                                                                      'sha256': '27bbc5f9f020fde78ff975ad1bc653fa117eb822d3e32f981901b0e43cac5126'},
 'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj': {'archive': 'scripts/dependency-predecessors/main-ebf-02.bin',
                                                                                        'bytes': 1182,
                                                                                        'gitBlob': 'c152c047af1ddb1bcedccf08b25d6a03320d34f3',
                                                                                        'sha256': 'd30612eef15d7e780e32dde8d14f4e7ad1ba821cc553f72a7e16930322185161'},
 'scripts/prepare-file-metadata-baseline.py': {'archive': 'scripts/dependency-predecessors/main-ebf-03.bin',
                                               'bytes': 13802,
                                               'gitBlob': '56f24eb9163a284a81b1a9d21b6a29f2f00adb6d',
                                               'sha256': '2776de9decd37817db4de088f5fb617762ad26f9114d4a9c934edb285f2f36f0'},
 'scripts/prepare-header-ignored-fields-baseline.py': {'archive': 'scripts/dependency-predecessors/main-ebf-04.bin',
                                                       'bytes': 29390,
                                                       'gitBlob': '9837224e836dff6b6a8ee2d3ba2e4ca49f6ec873',
                                                       'sha256': 'e9c5f5a94e6555e055907187bbc792ade61c0f863441b1b798a0c8c6f2d82d82'},
 'scripts/prepare-metadata-identity-baseline.py': {'archive': 'scripts/dependency-predecessors/main-ebf-05.bin',
                                                   'bytes': 26675,
                                                   'gitBlob': 'a3b423eaeee22bb5ba8893ef90b96b4cf08573f1',
                                                   'sha256': '35285329daf1a2b877b3ef51c68a5de04648cc0e02174fb647e8909547f53f2f'},
 'scripts/prepare-metadata-ignored-audits-baseline.py': {'archive': 'scripts/dependency-predecessors/main-ebf-06.bin',
                                                         'bytes': 27437,
                                                         'gitBlob': '4f1e2f7fb8c8767ef79b612320d78dee20674d70',
                                                         'sha256': '783ef496eca1ac96bc440b77d26ac797a3f4b6f32bc4cece834d2815b9f96381'},
 'scripts/prepare-supplier-identity-baseline.py': {'archive': 'scripts/dependency-predecessors/main-ebf-07.bin',
                                                   'bytes': 14624,
                                                   'gitBlob': 'b51d15c92ac269c86d2c24a0a601343f57364d2d',
                                                   'sha256': '174b6ae240b2382479dc748264f89294b1b755bd9d334fda17097419cd6bbe99'},
 'scripts/prepare-supplier-ignored-audits-baseline.py': {'archive': 'scripts/dependency-predecessors/main-ebf-08.bin',
                                                         'bytes': 28202,
                                                         'gitBlob': 'f5413a775d9fba84812d60533391e2d74bf599b7',
                                                         'sha256': '9e06de12b2d0c995a57f1a081b3c21fc3bf8c08059a76e5557c0c671a550e7cf'},
 'scripts/test_file_metadata_binding_results.py': {'archive': 'scripts/dependency-predecessors/main-ebf-09.bin',
                                                   'bytes': 37183,
                                                   'gitBlob': '93d47d4fe880add749a36de5376be1f10f540991',
                                                   'sha256': '3b2ca20eb125affbe8131d06f270562dd6e8ceeb1463a156a70e186522ee331f'},
 'scripts/test_header_ignored_fields_results.py': {'archive': 'scripts/dependency-predecessors/main-ebf-10.bin',
                                                   'bytes': 45772,
                                                   'gitBlob': 'e5483b80062a9ba7d222b096d92612415f4f23bc',
                                                   'sha256': 'ca0cce544c4ca25c0275a9aa0d400e7546cb39efe1ebe451014c94de034b64ea'},
 'scripts/test_metadata_identity_results.py': {'archive': 'scripts/dependency-predecessors/main-ebf-11.bin',
                                               'bytes': 47347,
                                               'gitBlob': '6d12f0c79633411dfa815fd0feb5741042e752d6',
                                               'sha256': '9e0862c6a4cb3d7c5960c89281bd7955f99554e271934ae75f2589b186593864'},
 'scripts/test_metadata_ignored_audits_results.py': {'archive': 'scripts/dependency-predecessors/main-ebf-12.bin',
                                                     'bytes': 46008,
                                                     'gitBlob': '3e7beb6aecb6df0ec20d9a37a6d7037310f8f697',
                                                     'sha256': '31866f1b45dfff003028780800e28fadd6b648546334498dd41dc79986179e22'},
 'scripts/test_po_header_hosted_red.py': {'archive': 'scripts/dependency-predecessors/main-ebf-13.bin',
                                          'bytes': 39025,
                                          'gitBlob': '67504b5e4727de73d13044b15262b7e8ddcb17f5',
                                          'sha256': '60c9dab1a3fa6b310281221d9bc625e37859e8c0cfaf38491af1a09aaf2259d4'},
 'scripts/test_procurement_address_null_consumer.py': {'archive': 'scripts/dependency-predecessors/main-ebf-14.bin',
                                                       'bytes': 20646,
                                                       'gitBlob': '6069d40cedf4b4f46d2bc29adcc3bad0c867b120',
                                                       'sha256': '34f0a4923f8dbcee49638b07f737b32c4e9fcbb5c762570332b74648cc48a689'},
 'scripts/test_procurement_auth_program_inputs.py': {'archive': 'scripts/dependency-predecessors/main-ebf-15.bin',
                                                     'bytes': 25546,
                                                     'gitBlob': '9fed6097fc3bf9214cb07589f32668cad92e5746',
                                                     'sha256': 'e6c1f1fa17fb64139ca2685faacedc1236e16db3545df29243b1ce032c2f7a41'},
 'scripts/test_supplier_identity_results.py': {'archive': 'scripts/dependency-predecessors/main-ebf-16.bin',
                                               'bytes': 31934,
                                               'gitBlob': 'da10ba96f75b89c14ab43eeef78d5a687597fd47',
                                               'sha256': '67f70c9a089cea19bc46437b92e5adabeffd2bb6cbb87f8c5925b9774daf0e6c'},
 'scripts/test_supplier_ignored_audits_results.py': {'archive': 'scripts/dependency-predecessors/main-ebf-17.bin',
                                                     'bytes': 45818,
                                                     'gitBlob': 'bc864396d9da3c8d074618b7280f347ea6755932',
                                                     'sha256': '7aa5d0256f7adbf8e61fb013b6c658f6418dd313115e0d25e471c9683e34fc52'},
 'scripts/verify-po-header-hosted-red.py': {'archive': 'scripts/dependency-predecessors/main-ebf-18.bin',
                                            'bytes': 33646,
                                            'gitBlob': '12c5f6affdf4eab174795b83d86daf7cdae07cd4',
                                            'sha256': 'b172876c2fb67c3142d20a7110beaca4ad1e4042b1abdd15921e4cbb59bc282b'},
 'scripts/verify-procurement-auth-program.py': {'archive': 'scripts/dependency-predecessors/main-ebf-19.bin',
                                                'bytes': 47226,
                                                'gitBlob': '1e5cb24cda948f01e16f9a7596fc0a426b601d21',
                                                'sha256': 'd472387f802ee02c8f8adefb8fa7add0ffa46912c97a1e6ea280a5e465f8a167'}}
TRANSFORMS = {'Directory.Build.props': [{'after': '    <PackageReference Update="Microsoft.EntityFrameworkCore" Version="10.0.13" '
                                     '/>\n'
                                     '    <PackageReference Update="Microsoft.EntityFrameworkCore.Relational" '
                                     'Version="10.0.13" />\n'
                                     '    <PackageReference Update="Microsoft.EntityFrameworkCore.Abstractions" '
                                     'Version="10.0.13" />\n',
                            'before': '    <PackageReference Update="Microsoft.EntityFrameworkCore" Version="10.0.12" '
                                      '/>\n'
                                      '    <PackageReference Update="Microsoft.EntityFrameworkCore.Relational" '
                                      'Version="10.0.12" />\n'
                                      '    <PackageReference Update="Microsoft.EntityFrameworkCore.Abstractions" '
                                      'Version="10.0.12" />\n',
                            'oldLineCount': 3,
                            'startLine': 7}],
 'Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj': [{'after': '    <PackageReference '
                                                                                                'Include="Microsoft.EntityFrameworkCore" '
                                                                                                'Version="10.0.13" />\n'
                                                                                                '    <PackageReference '
                                                                                                'Include="Microsoft.EntityFrameworkCore.Relational" '
                                                                                                'Version="10.0.13" '
                                                                                                '/>\n',
                                                                                       'before': '',
                                                                                       'oldLineCount': 0,
                                                                                       'startLine': 22}],
 'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj': [{'after': '    '
                                                                                                  '<PackageReference '
                                                                                                  'Include="Microsoft.EntityFrameworkCore.Design" '
                                                                                                  'Version="10.0.13">\n',
                                                                                         'before': '    '
                                                                                                   '<PackageReference '
                                                                                                   'Include="Microsoft.EntityFrameworkCore.Design" '
                                                                                                   'Version="10.0.12">\n',
                                                                                         'oldLineCount': 1,
                                                                                         'startLine': 9},
                                                                                        {'after': '    '
                                                                                                  '<PackageReference '
                                                                                                  'Include="Microsoft.Extensions.Caching.Abstractions" '
                                                                                                  'Version="10.0.13" '
                                                                                                  '/>\n'
                                                                                                  '    '
                                                                                                  '<PackageReference '
                                                                                                  'Include="Microsoft.Extensions.Logging.Abstractions" '
                                                                                                  'Version="10.0.13" '
                                                                                                  '/>\n',
                                                                                         'before': '    '
                                                                                                   '<PackageReference '
                                                                                                   'Include="Microsoft.Extensions.Caching.Abstractions" '
                                                                                                   'Version="10.0.12" '
                                                                                                   '/>\n'
                                                                                                   '    '
                                                                                                   '<PackageReference '
                                                                                                   'Include="Microsoft.Extensions.Logging.Abstractions" '
                                                                                                   'Version="10.0.12" '
                                                                                                   '/>\n',
                                                                                         'oldLineCount': 2,
                                                                                         'startLine': 13}],
 'scripts/prepare-file-metadata-baseline.py': [{'after': 'from procurement_dependency_consumer import '
                                                         '(dependency_runtime_blob, dependency_consumer_inputs,\n'
                                                         '    require_dependency_runtime, '
                                                         'current_dependency_script_binding, '
                                                         'authenticate_dependency)\n',
                                                'before': '',
                                                'oldLineCount': 0,
                                                'startLine': 1},
                                               {'after': '        require(blob(candidate, path) == '
                                                         'dependency_runtime_blob(path, '
                                                         'supplier_parent_audit_runtime_blob(path, '
                                                         'supplier_mutation_runtime_blob(path, expected))), "Candidate '
                                                         'runtime postimage differs: " + path)\n',
                                                'before': '        require(blob(candidate, path) == '
                                                          'supplier_parent_audit_runtime_blob(path, '
                                                          'supplier_mutation_runtime_blob(path, expected)), "Candidate '
                                                          'runtime postimage differs: " + path)\n',
                                                'oldLineCount': 1,
                                                'startLine': 117},
                                               {'after': '    authenticate_dependency(candidate, git)\n',
                                                'before': '',
                                                'oldLineCount': 0,
                                                'startLine': 160},
                                               {'after': '    require(changed == {PROGRAM, CONVERTER, API_PROJECT, '
                                                         'SUPPLIER_CONVERTER, METADATA_IDENTITY, HEADER, REPOSITORY, '
                                                         'SOURCE_FORMATTER, SOURCE_MODELS} | '
                                                         'set(SUPPLIER_QUERY_RUNTIME) | '
                                                         'require_supplier_mutation_runtime(candidate, blob) | '
                                                         'require_supplier_parent_audit_runtime(candidate, blob) | '
                                                         'require_health_alias_runtime(candidate, blob, git) | '
                                                         'require_dependency_runtime(candidate, blob, git), '
                                                         '"Unexpected production source changes")\n',
                                                'before': '    require(changed == {PROGRAM, CONVERTER, API_PROJECT, '
                                                          'SUPPLIER_CONVERTER, METADATA_IDENTITY, HEADER, REPOSITORY, '
                                                          'SOURCE_FORMATTER, SOURCE_MODELS} | '
                                                          'set(SUPPLIER_QUERY_RUNTIME) | '
                                                          'require_supplier_mutation_runtime(candidate, blob) | '
                                                          'require_supplier_parent_audit_runtime(candidate, blob) | '
                                                          'require_health_alias_runtime(candidate, blob, git), '
                                                          '"Unexpected production source changes")\n',
                                                'oldLineCount': 1,
                                                'startLine': 184}],
 'scripts/prepare-header-ignored-fields-baseline.py': [{'after': 'from procurement_dependency_consumer import '
                                                                 '(dependency_runtime_blob, '
                                                                 'dependency_consumer_inputs,\n'
                                                                 '    require_dependency_runtime, '
                                                                 'current_dependency_script_binding, '
                                                                 'authenticate_dependency)\n',
                                                        'before': '',
                                                        'oldLineCount': 0,
                                                        'startLine': 1},
                                                       {'after': '    authenticate_dependency(candidate, git)\n',
                                                        'before': '',
                                                        'oldLineCount': 0,
                                                        'startLine': 197},
                                                       {'after': '        require(blob(candidate, path) == '
                                                                 'current_dependency_script_binding(candidate, path, '
                                                                 'git_blob_record(record), blob, git)\n',
                                                        'before': '        require(blob(candidate, path) == '
                                                                  'git_blob_record(record)\n',
                                                        'oldLineCount': 1,
                                                        'startLine': 199},
                                                       {'after': '    authenticate_dependency(candidate, git)\n',
                                                        'before': '',
                                                        'oldLineCount': 0,
                                                        'startLine': 269},
                                                       {'after': '            and tracked_inputs(candidate, 74) == '
                                                                 'dependency_consumer_inputs(supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"])))), '
                                                                 '"Frozen72 baseline/reviewed74 input inventory '
                                                                 'differs")\n',
                                                        'before': '            and tracked_inputs(candidate, 74) == '
                                                                  'supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"]))), '
                                                                  '"Frozen72 baseline/reviewed74 input inventory '
                                                                  'differs")\n',
                                                        'oldLineCount': 1,
                                                        'startLine': 287},
                                                       {'after': '    current_inputs = '
                                                                 'dependency_consumer_inputs(supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"]))))\n',
                                                        'before': '    current_inputs = '
                                                                  'supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"])))\n',
                                                        'oldLineCount': 1,
                                                        'startLine': 320},
                                                       {'after': '    require(set(git(candidate, "diff", '
                                                                 '"--name-only", BASE, "HEAD", "--", '
                                                                 '*PROJECTS).decode().splitlines()) == {HEADER, '
                                                                 'REPOSITORY, SUPPLIER, METADATA_SEAM} | '
                                                                 'SOURCE_RUNTIME | set(SUPPLIER_QUERY_RUNTIME) | '
                                                                 'require_supplier_mutation_runtime(candidate, blob) | '
                                                                 'require_supplier_parent_audit_runtime(candidate, '
                                                                 'blob) | require_health_alias_runtime(candidate, '
                                                                 'blob, git) | require_dependency_runtime(candidate, '
                                                                 'blob, git),\n',
                                                        'before': '    require(set(git(candidate, "diff", '
                                                                  '"--name-only", BASE, "HEAD", "--", '
                                                                  '*PROJECTS).decode().splitlines()) == {HEADER, '
                                                                  'REPOSITORY, SUPPLIER, METADATA_SEAM} | '
                                                                  'SOURCE_RUNTIME | set(SUPPLIER_QUERY_RUNTIME) | '
                                                                  'require_supplier_mutation_runtime(candidate, blob) '
                                                                  '| require_supplier_parent_audit_runtime(candidate, '
                                                                  'blob) | require_health_alias_runtime(candidate, '
                                                                  'blob, git),\n',
                                                        'oldLineCount': 1,
                                                        'startLine': 347}],
 'scripts/prepare-metadata-identity-baseline.py': [{'after': 'from procurement_dependency_consumer import '
                                                             '(dependency_runtime_blob, dependency_consumer_inputs,\n'
                                                             '    require_dependency_runtime, '
                                                             'current_dependency_script_binding, '
                                                             'authenticate_dependency)\n',
                                                    'before': '',
                                                    'oldLineCount': 0,
                                                    'startLine': 1},
                                                   {'after': '        require(blob(candidate, path) == '
                                                             'dependency_runtime_blob(path, '
                                                             'supplier_parent_audit_runtime_blob(path, '
                                                             'supplier_mutation_runtime_blob(path, expected))), "Wrong '
                                                             'reviewed runtime postimage: " + path)\n',
                                                    'before': '        require(blob(candidate, path) == '
                                                              'supplier_parent_audit_runtime_blob(path, '
                                                              'supplier_mutation_runtime_blob(path, expected)), "Wrong '
                                                              'reviewed runtime postimage: " + path)\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 135},
                                                   {'after': '    authenticate_dependency(candidate, git)\n',
                                                    'before': '',
                                                    'oldLineCount': 0,
                                                    'startLine': 186},
                                                   {'after': '        require(blob(candidate, path) == '
                                                             'current_dependency_script_binding(candidate, path, '
                                                             'git_blob_record(record), blob, git)\n',
                                                    'before': '        require(blob(candidate, path) == '
                                                              'git_blob_record(record)\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 188},
                                                   {'after': '    authenticate_dependency(candidate, git)\n',
                                                    'before': '',
                                                    'oldLineCount': 0,
                                                    'startLine': 256},
                                                   {'after': '                and blob(candidate, path) == '
                                                             'dependency_runtime_blob(path, '
                                                             'candidate_binding["gitBlob"]), "Frozen candidate '
                                                             'fixture/build input differs")\n',
                                                    'before': '                and blob(candidate, path) == '
                                                              'candidate_binding["gitBlob"], "Frozen candidate '
                                                              'fixture/build input differs")\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 273},
                                                   {'after': '    require(set(git(candidate, "diff", "--name-only", '
                                                             'BASE, "HEAD", "--", *directories).decode().splitlines()) '
                                                             '== allowed | '
                                                             'require_supplier_mutation_runtime(candidate, blob) | '
                                                             'require_supplier_parent_audit_runtime(candidate, blob) | '
                                                             'require_health_alias_runtime(candidate, blob, git) | '
                                                             'require_dependency_runtime(candidate, blob, git),\n',
                                                    'before': '    require(set(git(candidate, "diff", "--name-only", '
                                                              'BASE, "HEAD", "--", '
                                                              '*directories).decode().splitlines()) == allowed | '
                                                              'require_supplier_mutation_runtime(candidate, blob) | '
                                                              'require_supplier_parent_audit_runtime(candidate, blob) '
                                                              '| require_health_alias_runtime(candidate, blob, git),\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 288}],
 'scripts/prepare-metadata-ignored-audits-baseline.py': [{'after': 'from procurement_dependency_consumer import '
                                                                   '(dependency_runtime_blob, '
                                                                   'dependency_consumer_inputs,\n'
                                                                   '    require_dependency_runtime, '
                                                                   'current_dependency_script_binding, '
                                                                   'authenticate_dependency)\n',
                                                          'before': '',
                                                          'oldLineCount': 0,
                                                          'startLine': 1},
                                                         {'after': '    authenticate_dependency(candidate, git)\n',
                                                          'before': '',
                                                          'oldLineCount': 0,
                                                          'startLine': 189},
                                                         {'after': '        require(blob(candidate, path) == '
                                                                   'current_dependency_script_binding(candidate, path, '
                                                                   'git_blob_record(record), blob, git)\n',
                                                          'before': '        require(blob(candidate, path) == '
                                                                    'git_blob_record(record)\n',
                                                          'oldLineCount': 1,
                                                          'startLine': 191},
                                                         {'after': '    authenticate_dependency(candidate, git)\n',
                                                          'before': '',
                                                          'oldLineCount': 0,
                                                          'startLine': 261},
                                                         {'after': '            and tracked_inputs(candidate, 74) == '
                                                                   'dependency_consumer_inputs(supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"])))), '
                                                                   '"Frozen72 baseline/reviewed74 input inventory '
                                                                   'differs")\n',
                                                          'before': '            and tracked_inputs(candidate, 74) == '
                                                                    'supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"]))), '
                                                                    '"Frozen72 baseline/reviewed74 input inventory '
                                                                    'differs")\n',
                                                          'oldLineCount': 1,
                                                          'startLine': 279},
                                                         {'after': '    current_inputs = '
                                                                   'dependency_consumer_inputs(supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"]))))\n',
                                                          'before': '    current_inputs = '
                                                                    'supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"])))\n',
                                                          'oldLineCount': 1,
                                                          'startLine': 302},
                                                         {'after': '    require(set(git(candidate, "diff", '
                                                                   '"--name-only", BASE, "HEAD", "--", '
                                                                   '*PROJECTS).decode().splitlines()) == {CONVERTER} | '
                                                                   'SOURCE_RUNTIME | set(SUPPLIER_QUERY_RUNTIME) | '
                                                                   'require_supplier_mutation_runtime(candidate, blob) '
                                                                   '| require_supplier_parent_audit_runtime(candidate, '
                                                                   'blob) | require_health_alias_runtime(candidate, '
                                                                   'blob, git) | require_dependency_runtime(candidate, '
                                                                   'blob, git),\n',
                                                          'before': '    require(set(git(candidate, "diff", '
                                                                    '"--name-only", BASE, "HEAD", "--", '
                                                                    '*PROJECTS).decode().splitlines()) == {CONVERTER} '
                                                                    '| SOURCE_RUNTIME | set(SUPPLIER_QUERY_RUNTIME) | '
                                                                    'require_supplier_mutation_runtime(candidate, '
                                                                    'blob) | '
                                                                    'require_supplier_parent_audit_runtime(candidate, '
                                                                    'blob) | require_health_alias_runtime(candidate, '
                                                                    'blob, git),\n',
                                                          'oldLineCount': 1,
                                                          'startLine': 329}],
 'scripts/prepare-supplier-identity-baseline.py': [{'after': 'from procurement_dependency_consumer import '
                                                             '(dependency_runtime_blob, dependency_consumer_inputs,\n'
                                                             '    require_dependency_runtime, '
                                                             'current_dependency_script_binding, '
                                                             'authenticate_dependency)\n',
                                                    'before': '',
                                                    'oldLineCount': 0,
                                                    'startLine': 1},
                                                   {'after': '        require(blob(candidate, path) == '
                                                             'dependency_runtime_blob(path, '
                                                             'supplier_parent_audit_runtime_blob(path, '
                                                             'supplier_mutation_runtime_blob(path, expected))), "Wrong '
                                                             'reviewed runtime postimage: " + path)\n',
                                                    'before': '        require(blob(candidate, path) == '
                                                              'supplier_parent_audit_runtime_blob(path, '
                                                              'supplier_mutation_runtime_blob(path, expected)), "Wrong '
                                                              'reviewed runtime postimage: " + path)\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 104},
                                                   {'after': '    authenticate_dependency(candidate, git)\n',
                                                    'before': '',
                                                    'oldLineCount': 0,
                                                    'startLine': 156},
                                                   {'after': '                and blob(candidate, path) == '
                                                             'dependency_runtime_blob(path, '
                                                             'candidate_binding["gitBlob"]), "Frozen candidate '
                                                             'fixture/build input differs")\n',
                                                    'before': '                and blob(candidate, path) == '
                                                              'candidate_binding["gitBlob"], "Frozen candidate '
                                                              'fixture/build input differs")\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 172},
                                                   {'after': '    require(set(git(candidate, "diff", "--name-only", '
                                                             'BASE, "HEAD", "--", *directories).decode().splitlines()) '
                                                             '== allowed | '
                                                             'require_supplier_mutation_runtime(candidate, blob) | '
                                                             'require_supplier_parent_audit_runtime(candidate, blob) | '
                                                             'require_health_alias_runtime(candidate, blob, git) | '
                                                             'require_dependency_runtime(candidate, blob, git),\n',
                                                    'before': '    require(set(git(candidate, "diff", "--name-only", '
                                                              'BASE, "HEAD", "--", '
                                                              '*directories).decode().splitlines()) == allowed | '
                                                              'require_supplier_mutation_runtime(candidate, blob) | '
                                                              'require_supplier_parent_audit_runtime(candidate, blob) '
                                                              '| require_health_alias_runtime(candidate, blob, git),\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 187}],
 'scripts/prepare-supplier-ignored-audits-baseline.py': [{'after': 'from procurement_dependency_consumer import '
                                                                   '(dependency_runtime_blob, '
                                                                   'dependency_consumer_inputs,\n'
                                                                   '    require_dependency_runtime, '
                                                                   'current_dependency_script_binding, '
                                                                   'authenticate_dependency)\n',
                                                          'before': '',
                                                          'oldLineCount': 0,
                                                          'startLine': 1},
                                                         {'after': '    authenticate_dependency(candidate, git)\n',
                                                          'before': '',
                                                          'oldLineCount': 0,
                                                          'startLine': 191},
                                                         {'after': '        require(blob(candidate, path) == '
                                                                   'current_dependency_script_binding(candidate, path, '
                                                                   'git_blob_record(record), blob, git)\n',
                                                          'before': '        require(blob(candidate, path) == '
                                                                    'git_blob_record(record)\n',
                                                          'oldLineCount': 1,
                                                          'startLine': 193},
                                                         {'after': '    authenticate_dependency(candidate, git)\n',
                                                          'before': '',
                                                          'oldLineCount': 0,
                                                          'startLine': 263},
                                                         {'after': '            and tracked_inputs(candidate, 74) == '
                                                                   'dependency_consumer_inputs(supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"])))), '
                                                                   '"Frozen72 baseline/reviewed74 input inventory '
                                                                   'differs")\n',
                                                          'before': '            and tracked_inputs(candidate, 74) == '
                                                                    'supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"]))), '
                                                                    '"Frozen72 baseline/reviewed74 input inventory '
                                                                    'differs")\n',
                                                          'oldLineCount': 1,
                                                          'startLine': 281},
                                                         {'after': '    current_inputs = '
                                                                   'dependency_consumer_inputs(supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"]))))\n',
                                                          'before': '    current_inputs = '
                                                                    'supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(manifest["reviewedInputs"])))\n',
                                                          'oldLineCount': 1,
                                                          'startLine': 309},
                                                         {'after': '    require(set(git(candidate, "diff", '
                                                                   '"--name-only", BASE, "HEAD", "--", '
                                                                   '*PROJECTS).decode().splitlines()) == {CONVERTER, '
                                                                   'METADATA_SEAM} | SOURCE_RUNTIME | '
                                                                   'set(SUPPLIER_QUERY_RUNTIME) | '
                                                                   'require_supplier_mutation_runtime(candidate, blob) '
                                                                   '| require_supplier_parent_audit_runtime(candidate, '
                                                                   'blob) | require_health_alias_runtime(candidate, '
                                                                   'blob, git) | require_dependency_runtime(candidate, '
                                                                   'blob, git),\n',
                                                          'before': '    require(set(git(candidate, "diff", '
                                                                    '"--name-only", BASE, "HEAD", "--", '
                                                                    '*PROJECTS).decode().splitlines()) == {CONVERTER, '
                                                                    'METADATA_SEAM} | SOURCE_RUNTIME | '
                                                                    'set(SUPPLIER_QUERY_RUNTIME) | '
                                                                    'require_supplier_mutation_runtime(candidate, '
                                                                    'blob) | '
                                                                    'require_supplier_parent_audit_runtime(candidate, '
                                                                    'blob) | require_health_alias_runtime(candidate, '
                                                                    'blob, git),\n',
                                                          'oldLineCount': 1,
                                                          'startLine': 336}],
 'scripts/test_file_metadata_binding_results.py': [{'after': 'from procurement_dependency_consumer import '
                                                             'historical_scripts\n'
                                                             'from test_procurement_dependency_consumer import '
                                                             'DependencyConsumerControls\n'
                                                             'HISTORICAL_SCRIPTS = historical_scripts(__file__)\n'
                                                             '\n'
                                                             'SPEC = '
                                                             'importlib.util.spec_from_file_location("metadata", '
                                                             '(HISTORICAL_SCRIPTS / '
                                                             '"verify-file-metadata-binding-results.py"))\n',
                                                    'before': 'SPEC = '
                                                              'importlib.util.spec_from_file_location("metadata", '
                                                              'pathlib.Path(__file__).with_name("verify-file-metadata-binding-results.py"))\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 19},
                                                   {'after': 'PREP_SPEC = '
                                                             'importlib.util.spec_from_file_location("metadata_source", '
                                                             '(HISTORICAL_SCRIPTS / '
                                                             '"prepare-file-metadata-baseline.py"))\n',
                                                    'before': 'PREP_SPEC = '
                                                              'importlib.util.spec_from_file_location("metadata_source", '
                                                              'pathlib.Path(__file__).with_name("prepare-file-metadata-baseline.py"))\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 26},
                                                   {'after': 'OBS_SPEC = '
                                                             'importlib.util.spec_from_file_location("metadata_observer", '
                                                             '(HISTORICAL_SCRIPTS / '
                                                             '"observe-file-metadata-providers.py"))\n',
                                                    'before': 'OBS_SPEC = '
                                                              'importlib.util.spec_from_file_location("metadata_observer", '
                                                              'pathlib.Path(__file__).with_name("observe-file-metadata-providers.py"))\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 30}],
 'scripts/test_header_ignored_fields_results.py': [{'after': 'from procurement_dependency_consumer import '
                                                             'historical_scripts\n'
                                                             'from test_procurement_dependency_consumer import '
                                                             'DependencyConsumerControls\n'
                                                             'HERE = historical_scripts(__file__)\n',
                                                    'before': 'HERE = pathlib.Path(__file__).resolve().parent\n',
                                                    'oldLineCount': 1,
                                                    'startLine': 19}],
 'scripts/test_metadata_identity_results.py': [{'after': 'from procurement_dependency_consumer import '
                                                         'historical_scripts\n'
                                                         'from test_procurement_dependency_consumer import '
                                                         'DependencyConsumerControls\n'
                                                         'HERE = historical_scripts(__file__)\n',
                                                'before': 'HERE = pathlib.Path(__file__).resolve().parent\n',
                                                'oldLineCount': 1,
                                                'startLine': 19}],
 'scripts/test_metadata_ignored_audits_results.py': [{'after': 'from procurement_dependency_consumer import '
                                                               'historical_scripts\n'
                                                               'from test_procurement_dependency_consumer import '
                                                               'DependencyConsumerControls\n'
                                                               'HERE = historical_scripts(__file__)\n',
                                                      'before': 'HERE = pathlib.Path(__file__).resolve().parent\n',
                                                      'oldLineCount': 1,
                                                      'startLine': 19}],
 'scripts/test_po_header_hosted_red.py': [{'after': 'from procurement_dependency_consumer import historical_scripts\n'
                                                    'from test_procurement_dependency_consumer import '
                                                    'DependencyConsumerControls\n'
                                                    'MODULE_PATH = historical_scripts(__file__) / '
                                                    '"verify-po-header-hosted-red.py"\n',
                                           'before': 'MODULE_PATH = '
                                                     'Path(__file__).with_name("verify-po-header-hosted-red.py")\n',
                                           'oldLineCount': 1,
                                           'startLine': 13}],
 'scripts/test_procurement_address_null_consumer.py': [{'after': 'from procurement_dependency_consumer import '
                                                                 'historical_scripts\n'
                                                                 'HERE = historical_scripts(__file__)\n',
                                                        'before': 'HERE = pathlib.Path(__file__).resolve().parent\n',
                                                        'oldLineCount': 1,
                                                        'startLine': 9}],
 'scripts/test_procurement_auth_program_inputs.py': [{'after': 'from procurement_dependency_consumer import '
                                                               'historical_scripts\n'
                                                               'from test_procurement_dependency_consumer import '
                                                               'DependencyConsumerControls\n'
                                                               'HISTORICAL_SCRIPTS = historical_scripts(__file__)\n'
                                                               '\n'
                                                               'spec = '
                                                               'importlib.util.spec_from_file_location("join_guard", '
                                                               '(HISTORICAL_SCRIPTS / '
                                                               '"verify-procurement-auth-program.py"))\n',
                                                      'before': 'spec = '
                                                                'importlib.util.spec_from_file_location("join_guard", '
                                                                'pathlib.Path(__file__).with_name("verify-procurement-auth-program.py"))\n',
                                                      'oldLineCount': 1,
                                                      'startLine': 9}],
 'scripts/test_supplier_identity_results.py': [{'after': 'from procurement_dependency_consumer import '
                                                         'historical_scripts\n'
                                                         'from test_procurement_dependency_consumer import '
                                                         'DependencyConsumerControls\n'
                                                         'HERE = historical_scripts(__file__)\n',
                                                'before': 'HERE = pathlib.Path(__file__).resolve().parent\n',
                                                'oldLineCount': 1,
                                                'startLine': 18}],
 'scripts/test_supplier_ignored_audits_results.py': [{'after': 'from procurement_dependency_consumer import '
                                                               'historical_scripts\n'
                                                               'from test_procurement_dependency_consumer import '
                                                               'DependencyConsumerControls\n'
                                                               'HERE = historical_scripts(__file__)\n',
                                                      'before': 'HERE = pathlib.Path(__file__).resolve().parent\n',
                                                      'oldLineCount': 1,
                                                      'startLine': 19}],
 'scripts/verify-po-header-hosted-red.py': [{'after': 'from procurement_dependency_consumer import '
                                                      'authenticate_dependency, dependency_restoration_digests\n',
                                             'before': '',
                                             'oldLineCount': 0,
                                             'startLine': 1},
                                            {'after': '    authenticate_dependency(root, git)\n',
                                             'before': '',
                                             'oldLineCount': 0,
                                             'startLine': 255},
                                            {'after': '    for relative, expected in '
                                                      'dependency_restoration_digests(root, '
                                                      'candidate_digests(contract), git).items():\n',
                                             'before': '    for relative, expected in '
                                                       'candidate_digests(contract).items():\n',
                                             'oldLineCount': 1,
                                             'startLine': 256},
                                            {'after': '    reviewed_digests = dependency_restoration_digests(root, '
                                                      'candidate_digests(contract), git)\n',
                                             'before': '    reviewed_digests = candidate_digests(contract)\n',
                                             'oldLineCount': 1,
                                             'startLine': 266}],
 'scripts/verify-procurement-auth-program.py': [{'after': 'from procurement_dependency_consumer import '
                                                          '(dependency_runtime_blob, dependency_consumer_inputs,\n'
                                                          '    require_dependency_runtime, '
                                                          'current_dependency_script_binding, '
                                                          'authenticate_dependency)\n',
                                                 'before': '',
                                                 'oldLineCount': 0,
                                                 'startLine': 1},
                                                {'after': '    require_equal(health_alias_previous_inputs(current), '
                                                          'dependency_consumer_inputs(supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(observation_consumer_inputs(expected))))))\n',
                                                 'before': '    require_equal(health_alias_previous_inputs(current), '
                                                           'supplier_parent_audit_consumer_inputs(supplier_mutation_consumer_inputs(address_consumer_inputs(observation_consumer_inputs(expected)))))\n',
                                                 'oldLineCount': 1,
                                                 'startLine': 92},
                                                {'after': '    authenticate_dependency(ROOT)\n',
                                                 'before': '',
                                                 'oldLineCount': 0,
                                                 'startLine': 112}]}
DEPENDENCIES = {'Directory.Build.props': {'after': 'da83d69d946c60539143c7009ffa5adc953f76ad',
                           'before': 'b47c8d23651f11ea8366bb63f4520fb8de6c6df3'},
 'Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj': {'after': 'd8f61ede45680c9c8f88ba3d2d38f3e0932516a0',
                                                                                      'before': '30c131eb10c554b445e878c0b148cbe79d8c7cd3'},
 'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj': {'after': '812c4723e641296057f65e7550356995424f72ee',
                                                                                        'before': 'c152c047af1ddb1bcedccf08b25d6a03320d34f3'}}
PROTECTED = ['Directory.Build.props', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementIamComposition.cs', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementPermissions.cs', 'Legacy.Maliev.ProcurementService.Api/Authorization/ProcurementWorkloadExchangeGuard.cs', 'Legacy.Maliev.ProcurementService.Api/Controllers/FilesController.cs', 'Legacy.Maliev.ProcurementService.Api/Controllers/LegacyProcurementHealthController.cs', 'Legacy.Maliev.ProcurementService.Api/Controllers/OrderItemsController.cs', 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrderAddressesController.cs', 'Legacy.Maliev.ProcurementService.Api/Controllers/PurchaseOrdersController.cs', 'Legacy.Maliev.ProcurementService.Api/Controllers/SupplierAddressesController.cs', 'Legacy.Maliev.ProcurementService.Api/Controllers/SuppliersController.cs', 'Legacy.Maliev.ProcurementService.Api/Dockerfile', 'Legacy.Maliev.ProcurementService.Api/DurableChildCreateEndpoint.cs', 'Legacy.Maliev.ProcurementService.Api/DurableCreateEndpoint.cs', 'Legacy.Maliev.ProcurementService.Api/IdempotentCreates.cs', 'Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj', 'Legacy.Maliev.ProcurementService.Api/Program.cs', 'Legacy.Maliev.ProcurementService.Api/Properties/launchSettings.json', 'Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementIgnoredBodyIdJsonOptions.cs', 'Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementOriginalBodyModels.cs', 'Legacy.Maliev.ProcurementService.Api/Serialization/ProcurementSourceBodyInputFormatter.cs', 'Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderFileMetadataRequestJsonConverter.cs', 'Legacy.Maliev.ProcurementService.Api/Serialization/PurchaseOrderHeaderRequestJsonConverter.cs', 'Legacy.Maliev.ProcurementService.Api/Serialization/SupplierIgnoredIdJsonConverter.cs', 'Legacy.Maliev.ProcurementService.Api/appsettings.Development.json', 'Legacy.Maliev.ProcurementService.Api/appsettings.json', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementChildCreates.cs', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IDurableProcurementCreates.cs', 'Legacy.Maliev.ProcurementService.Application/Interfaces/IProcurementBoundaries.cs', 'Legacy.Maliev.ProcurementService.Application/Legacy.Maliev.ProcurementService.Application.csproj', 'Legacy.Maliev.ProcurementService.Application/Models/DurableCreateModels.cs', 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementModels.cs', 'Legacy.Maliev.ProcurementService.Application/Models/ProcurementTransactionUncertainException.cs', 'Legacy.Maliev.ProcurementService.Application/Models/PurchaseOrderAddressScalarStringJsonConverter.cs', 'Legacy.Maliev.ProcurementService.Application/Models/SupplierAddressScalarStringJsonConverter.cs', 'Legacy.Maliev.ProcurementService.Application/Models/SupplierScalarStringJsonConverter.cs', 'Legacy.Maliev.ProcurementService.Application/Services/ProcurementApplicationServices.cs', 'Legacy.Maliev.ProcurementService.Data/ChildReceiptRecords.cs', 'Legacy.Maliev.ProcurementService.Data/CreateReceiptRecord.cs', 'Legacy.Maliev.ProcurementService.Data/DistributedProcurementCache.cs', 'Legacy.Maliev.ProcurementService.Data/DurableProcurementChildCreates.cs', 'Legacy.Maliev.ProcurementService.Data/DurableProcurementCreates.cs', 'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj', 'Legacy.Maliev.ProcurementService.Data/LegacyUtf16StringStorage.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260715045323_InitialPurchaseOrderPostgresCompatibility.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20260721031258_FixTimestampColumnType.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261001013651_AddDurablePurchaseOrderCreateReceipts.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261006210000_PreservePurchaseOrderSourceStringBoundaries.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/20261011073000_AddDurablePurchaseOrderChildReceipts.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/PurchaseOrder/PurchaseOrderDbContextModelSnapshot.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260715045317_InitialSupplierPostgresCompatibility.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20260721031252_FixTimestampColumnType.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261001013648_AddDurableSupplierCreateReceipts.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.Designer.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/20261006210000_PreserveSupplierSourceStringBoundaries.cs', 'Legacy.Maliev.ProcurementService.Data/Migrations/Supplier/SupplierDbContextModelSnapshot.cs', 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContextFactories.cs', 'Legacy.Maliev.ProcurementService.Data/ProcurementDbContexts.cs', 'Legacy.Maliev.ProcurementService.Data/ProcurementRepositories.cs', 'Legacy.Maliev.ProcurementService.Data/PurchaseOrderFileSourceConstraints.cs', 'Legacy.Maliev.ProcurementService.Data/ReceiptReadiness.cs', 'Legacy.Maliev.ProcurementService.Domain/Legacy.Maliev.ProcurementService.Domain.csproj', 'Legacy.Maliev.ProcurementService.Domain/ProcurementEntities.cs', 'Legacy.Maliev.ProcurementService.Tests/Integration/ProcurementRuntimeParityTests.cs', 'Legacy.Maliev.ProcurementService.Tests/Legacy.Maliev.ProcurementService.Tests.csproj', 'docs/procurement-file-metadata-binding-contract.json', 'docs/procurement-focused-lifecycle-contract.json', 'docs/procurement-focused-workflow-contract.json', 'docs/procurement-header-ignored-fields-contract.json', 'docs/procurement-master-query-contract.json', 'docs/procurement-metadata-identity-contract.json', 'docs/procurement-metadata-ignored-audits-contract.json', 'docs/procurement-po-header-hosted-red-contract.json', 'docs/procurement-supplier-address-causal-contract.json', 'docs/procurement-supplier-identity-contract.json', 'docs/procurement-supplier-ignored-audits-contract.json', 'scripts/observe-file-metadata-providers.py', 'scripts/observe-header-ignored-fields-providers.py', 'scripts/observe-metadata-identity-providers.py', 'scripts/observe-metadata-ignored-audits-providers.py', 'scripts/observe-supplier-address-providers.py', 'scripts/observe-supplier-identity-providers.py', 'scripts/observe-supplier-ignored-audits-providers.py', 'scripts/prepare-file-metadata-baseline.py', 'scripts/prepare-header-ignored-fields-baseline.py', 'scripts/prepare-metadata-identity-baseline.py', 'scripts/prepare-metadata-ignored-audits-baseline.py', 'scripts/prepare-supplier-address-causal-baseline.py', 'scripts/prepare-supplier-identity-baseline.py', 'scripts/prepare-supplier-ignored-audits-baseline.py', 'scripts/procurement_address_null_consumer.py', 'scripts/procurement_artifact_transport_consumer.py', 'scripts/require-metadata-identity-admission.py', 'scripts/supplier_address_owned_processes.py', 'scripts/test_file_metadata_binding_results.py', 'scripts/test_focused_workflow_results.py', 'scripts/test_header_ignored_fields_results.py', 'scripts/test_metadata_identity_results.py', 'scripts/test_metadata_ignored_audits_results.py', 'scripts/test_po_header_hosted_red.py', 'scripts/test_procurement_address_null_consumer.py', 'scripts/test_procurement_artifact_transport_consumer.py', 'scripts/test_procurement_auth_program_inputs.py', 'scripts/test_procurement_health_aliases.py', 'scripts/test_procurement_string_boundaries.py', 'scripts/test_query_fixture_encoding.py', 'scripts/test_supplier_address_causal_results.py', 'scripts/test_supplier_address_provider_observation.py', 'scripts/test_supplier_identity_results.py', 'scripts/test_supplier_ignored_audits_results.py', 'scripts/test_supplier_parent_audit_consumer.py', 'scripts/test_supplier_parent_audit_harness_consumer.py', 'scripts/tests/test_dormant_deployment.py', 'scripts/verify-file-metadata-binding-results.py', 'scripts/verify-focused-lifecycle-results.py', 'scripts/verify-focused-workflow-results.py', 'scripts/verify-header-ignored-fields-results.py', 'scripts/verify-master-query-results.py', 'scripts/verify-metadata-identity-results.py', 'scripts/verify-metadata-ignored-audits-results.py', 'scripts/verify-po-header-hosted-red.py', 'scripts/verify-procurement-auth-program.py', 'scripts/verify-procurement-defaults-deadline.py', 'scripts/verify-procurement-health-aliases.py', 'scripts/verify-procurement-literal-boundaries.py', 'scripts/verify-procurement-nullable-sorts.py', 'scripts/verify-procurement-string-boundaries.py', 'scripts/verify-purchase-order-header-results.py', 'scripts/verify-query-fixture-encoding.py', 'scripts/verify-runner-coverage.py', 'scripts/verify-supplier-address-causal-results.py', 'scripts/verify-supplier-identity-results.py', 'scripts/verify-supplier-ignored-audits-results.py', 'tools/ProcurementAuthProgram.Tests/public-graph-accepted-9c801.json', 'tools/ProcurementAuthProgram.Tests/public-graph-address-country-id.json', 'tools/ProcurementAuthProgram.Tests/public-graph-child-replay.json', 'tools/ProcurementAuthProgram.Tests/public-graph-file-bucket.json', 'tools/ProcurementAuthProgram.Tests/public-graph-file-metadata-binding.json', 'tools/ProcurementAuthProgram.Tests/public-graph-header-contact-ignored-fields.json', 'tools/ProcurementAuthProgram.Tests/public-graph-header-ignored-fields.json', 'tools/ProcurementAuthProgram.Tests/public-graph-metadata-ignored-audits.json', 'tools/ProcurementAuthProgram.Tests/public-graph-metadata-ignored-identity.json', 'tools/ProcurementAuthProgram.Tests/public-graph-purchase-order-address.json', 'tools/ProcurementAuthProgram.Tests/public-graph-source-body-input.json', 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-address.json', 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-ignored-audits.json', 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-ignored-identity.json', 'tools/ProcurementAuthProgram.Tests/public-graph-supplier-omitted-size.json', 'tools/ProcurementAuthProgram.Tests/public-graph.json']
CHECKOUTS = {'docs/Invoke-StartupArtifactProof.ps1': {'archiveBlob': '09a0611d4dc205b4e5f6b1322b7e855641c032c1',
                                          'archiveBytes': 6698,
                                          'basis': 'Exact committed *.ps1 text eol=crlf attribute; source inspection '
                                                   'only, no runtime guard normalization added',
                                          'gitBlob': '95d182aa50fedc6ee5f0b8c204b9899d7df744f3',
                                          'gitBytes': 6590,
                                          'path': 'docs/Invoke-StartupArtifactProof.ps1'},
 'scripts/Render-DormantLegacyProcurementDeployment.ps1': {'archiveBlob': 'ce5eaa9fbdc5bdd0bbf88fbce8af572331b9a594',
                                                           'archiveBytes': 1853,
                                                           'basis': 'Exact committed *.ps1 text eol=crlf attribute; '
                                                                    'source inspection only, no runtime guard '
                                                                    'normalization added',
                                                           'gitBlob': '6dab02dceb64cfa552502ba0236a8c21e4992690',
                                                           'gitBytes': 1822,
                                                           'path': 'scripts/Render-DormantLegacyProcurementDeployment.ps1'}}
CONTROL_SHA256 = '1a2d234661a03ebe637e97a6e904f24b6e58e2cb77df642a256e90b8a6e017ae'
# END CLOSED CONSTANTS

MODULE='scripts/procurement_dependency_consumer.py'
CONTROLS='scripts/test_procurement_dependency_consumer.py'
PROFILE='scripts/procurement-dependency-source-profile.json'
VIEWS=[]

def need(value,message):
    if not value:raise ValueError('Dependency consumer: '+message)

def same(a,b):return json.dumps(a,sort_keys=True,separators=(',',':'))==json.dumps(b,sort_keys=True,separators=(',',':'))

def blob_bytes(raw):return hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()

def record(raw):return dict(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),gitBlob=blob_bytes(raw))

def read(root,name):
    need(isinstance(name,str) and '\\' not in name and ':' not in name and all(p not in ('','.','..') for p in name.split('/')),'closed relative path')
    root=Path(root);path=root/name
    for node in (path,*path.parents):
        if node==root.parent:break
        need(not node.is_symlink() and not (hasattr(node,'is_junction') and node.is_junction()),'source link refused')
    before=path.lstat();identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
    need(stat.S_ISREG(before.st_mode) and before.st_nlink==1 and 0<before.st_size<=1048576,'bounded regular source')
    with path.open('rb') as stream:
        need(identity(os.fstat(stream.fileno()))==identity(before),'source replaced before read')
        raw=stream.read(1048577)
        need(identity(os.fstat(stream.fileno()))==identity(before),'source changed during read')
    need(len(raw)==before.st_size and identity(path.lstat())==identity(before),'source replaced after read')
    return raw

LOADED_MODULE_BYTES=read(Path(__file__).resolve().parents[1],MODULE)

def parse(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            need(key not in result,'duplicate JSON field');result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique)

def archived(root,name):
    row=ARCHIVES[name];raw=read(root,row['archive'])
    need(same(record(raw),{k:row[k] for k in ('bytes','sha256','gitBlob')}),'immutable predecessor: '+name)
    return raw

def transformed(root,name):
    lines=archived(root,name).splitlines(keepends=True)
    for edit in reversed(TRANSFORMS[name]):
        at=edit['startLine']-1
        need(b''.join(lines[at:at+edit['oldLineCount']])==edit['before'].encode(),'fixed source preimage')
        lines[at:at+edit['oldLineCount']]=[edit['after'].encode()]
    return b''.join(lines)

def expected_profile(root):
    return dict(schemaVersion=1,profile='procurement-ef13-current-consumer',predecessorMain=MAIN,
        currentChanges=[dict(path=p,predecessor=ORIGINAL[p],current=record(transformed(root,p))) for p in sorted(TRANSFORMS)],
        additionalInputs=[dict(path=p,**record(read(root,p))) for p in sorted({MODULE,CONTROLS}|{v['archive'] for v in ARCHIVES.values()})],
        executionGranted=False,sdkGranted=False,runtimeQualified=False)

def canonical_blob(name,raw):
    row=CHECKOUTS.get(name)
    if row and blob_bytes(raw)==row['archiveBlob'] and len(raw)==row['archiveBytes']:return row['gitBlob']
    return blob_bytes(raw)

def metadata_git(root,*args):
    with tempfile.TemporaryFile() as output:
        subprocess.run(['git','-C',str(root),*args],stdout=output,check=True,timeout=10)
        output.seek(0);raw=output.read(4*1024*1024+1)
    need(len(raw)<=4*1024*1024,'Git metadata byte bound')
    return raw

def process_identity():
    if os.name=='nt':
        from ctypes import wintypes as w
        k=ctypes.WinDLL('kernel32',use_last_error=True);k.GetCurrentProcess.restype=w.HANDLE
        k.GetProcessTimes.argtypes=[w.HANDLE,*([ctypes.POINTER(w.FILETIME)]*4)];times=[w.FILETIME() for _ in range(4)]
        need(k.GetProcessTimes(k.GetCurrentProcess(),*[ctypes.byref(t) for t in times]),'own process identity')
        return dict(pid=os.getpid(),creationFileTime100ns=(times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)
    return dict(pid=os.getpid(),bootId=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),startTicks=Path('/proc/self/stat').read_text().rsplit(') ',1)[1].split()[19])

def _authenticate_bytes(root):
    need(read(root,MODULE)==LOADED_MODULE_BYTES,'loaded dependency verifier changed')
    need(hashlib.sha256(read(root,CONTROLS)).hexdigest()==CONTROL_SHA256,'exact dependency controls')
    profile=parse(read(root,PROFILE))
    need(same(profile,expected_profile(root)),'closed source profile/false grants')
    for name in ARCHIVES:archived(root,name)
    expected={}
    for name in PROTECTED:
        raw=transformed(root,name) if name in TRANSFORMS else read(root,name)
        need(read(root,name)==raw,'fixed current source: '+name)
        if name not in TRANSFORMS:need(same(record(raw),ORIGINAL[name]),'retained input changed: '+name)
        expected[name]=canonical_blob(name,raw)
    extra={MODULE,CONTROLS,PROFILE}|{v['archive'] for v in ARCHIVES.values()}
    expected.update({name:blob_bytes(read(root,name)) for name in extra})
    return profile,expected,extra

def authenticate_dependency(root,git=None):
    profile,expected,extra=_authenticate_bytes(root)
    query=git or metadata_git
    raw=query(root,'ls-tree','-r','-z','HEAD')
    need(len(raw)<=4*1024*1024,'current Git metadata byte bound')
    observed={}
    for item in raw.split(b'\0'):
        if item:
            info,name=item.split(b'\t',1);observed[name.decode()]=info.decode()
    need(set(observed)==set(ORIGINAL)|extra,'exact tracked source roster')
    for name,digest in expected.items():need(observed.get(name)=='100644 blob '+digest,'current working/HEAD source differs: '+name)
    return profile

def dependency_runtime_blob(path,previous):
    if path not in DEPENDENCIES:return previous
    need(previous==DEPENDENCIES[path]['before'],'exact dependency preimage: '+path)
    return DEPENDENCIES[path]['after']

def dependency_consumer_inputs(previous):
    need(isinstance(previous,dict),'source input map')
    current=dict(previous)
    for path,row in DEPENDENCIES.items():
        need(current.get(path)=='100644 blob '+row['before'],'exact current-map preimage: '+path)
        current[path]='100644 blob '+row['after']
    return current

def require_dependency_runtime(candidate,blob=None,git=None):
    authenticate_dependency(candidate,git)
    return {'Legacy.Maliev.ProcurementService.Data/Legacy.Maliev.ProcurementService.Data.csproj'}

def current_dependency_script_binding(candidate,path,previous,blob,git):
    # The unchanged per-row working/HEAD equalities remain at the caller;
    # require_script_bindings authenticates this complete source profile once.
    if path not in TRANSFORMS:return previous
    need(previous==ORIGINAL[path]['gitBlob'],'exact historical script binding')
    return blob_bytes(transformed(candidate,path))

def dependency_restoration_digests(root,previous,git=None):
    # A PO RED intentionally replaces Program/removes one converter. Authenticate
    # only fixed build inputs, hooks, controls and immutable manifests here;
    # the original restore loop restores and verifies ALL eleven current sources.
    need(read(root,MODULE)==LOADED_MODULE_BYTES,'loaded dependency verifier changed')
    need(hashlib.sha256(read(root,CONTROLS)).hexdigest()==CONTROL_SHA256,'exact dependency controls')
    need(same(parse(read(root,PROFILE)),expected_profile(root)),'closed restoration source profile')
    for name in TRANSFORMS:need(read(root,name)==transformed(root,name),'fixed restoration dependency/hook source')
    query=git or metadata_git
    for name,row in DEPENDENCIES.items():
        need(query(root,'rev-parse','HEAD:'+name).decode().strip()==row['after'],'restoration dependency working/HEAD differs')
    for name in PROTECTED:
        if name.startswith(('docs/','scripts/','tools/ProcurementAuthProgram.Tests/public-graph')) and name not in TRANSFORMS:
            need(same(record(read(root,name)),ORIGINAL[name]),'retained restoration witness')
    path='Legacy.Maliev.ProcurementService.Api/Legacy.Maliev.ProcurementService.Api.csproj'
    need(type(previous) is dict and len(previous)==11 and previous.get(path)==ORIGINAL[path]['sha256'],'exact eleven-source API preimage')
    result=dict(previous);result[path]=hashlib.sha256(transformed(root,path)).hexdigest()
    return result

@contextlib.contextmanager
def historical_view(root,git=None):
    # Pure historical assertions authenticate bytes, not synthetic Git HEAD.
    # Real admission never calls this projection and always checks actual HEAD.
    _authenticate_bytes(root)
    parent=Path(root).resolve().parent
    with tempfile.TemporaryDirectory(prefix='.procurement-dependency-ebf-',dir=parent) as temporary:
        owner=Path(temporary);need(owner.resolve().parent==parent,'owned historical view')
        (owner/'task-owner.json').write_text(json.dumps(dict(task='Procurement59-historical-tests',process=process_identity(),created=time.time(),leaseSeconds=120)))
        target=owner/'source';target.mkdir()
        for name,row in ORIGINAL.items():
            raw=archived(root,name) if name in ARCHIVES else read(root,name)
            need(same(record(raw),row),'bound historical source: '+name)
            destination=target/name;destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw)
        # Old source assertions that read Git metadata get a real task-owned
        # source snapshot with the EXACT accepted main tree, never fake HEAD data.
        environment=os.environ.copy();environment.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL=os.devnull,GIT_TERMINAL_PROMPT='0')
        def run(*args,input=None):
            return subprocess.check_output(['git','-c','core.autocrlf=false','-c','core.hooksPath='+str(owner/'disabled-hooks'),'-C',str(target),*args],input=input,env=environment,stderr=subprocess.PIPE,timeout=15)
        run('init','--initial-branch=historical-source-test')
        run('config','core.longpaths','true')
        # One real Git import avoids a slow repeated worktree/index scan. Blob
        # bodies use authenticated lengths; paths come only from the sealed map.
        stream=bytearray();marks=[]
        for index,name in enumerate(sorted(ORIGINAL),1):
            need(not any(c in name for c in ('\n','\r','\0','"')),'closed historical Git path')
            raw=read(target,name)
            if name in CHECKOUTS:raw=raw.replace(b'\r\n',b'\n')
            need(blob_bytes(raw)==canonical_blob(name,read(target,name)),'exact historical Git blob')
            stream.extend(f'blob\nmark :{index}\ndata {len(raw)}\n'.encode()+raw+b'\n');marks.append((index,name))
        message=b'Unpublished exact predecessor source fixture'
        stream.extend(b'commit refs/heads/historical-source-test\ncommitter Procurement source controls <source-controls@example.invalid> 0 +0000\ndata '+str(len(message)).encode()+b'\n'+message+b'\n')
        for index,name in marks:stream.extend(f'M 100644 :{index} {name}\n'.encode())
        stream.extend(b'\ndone\n')
        run('fast-import','--quiet',input=bytes(stream))
        need(run('rev-parse','HEAD^{tree}').decode().strip()==MAIN_TREE,'exact accepted historical Git tree')
        yield target

def historical_scripts(script):
    root=Path(script).resolve().parents[1]
    owner=historical_view(root)
    view=owner.__enter__();VIEWS.append(owner)
    atexit.unregister(close_views);atexit.register(close_views)
    return view/'scripts'

def close_views():
    while VIEWS:VIEWS.pop().__exit__(None,None,None)

atexit.register(close_views)
