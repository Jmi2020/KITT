{
  "openapi": "3.0.1",
  "info": {
    "title": "Tripo 3D Generation",
    "description": "use tripo to generate 3d models",
    "version": "1.0.0"
  },
  "servers": [
    {
      "url": "https://api.tripo3d.ai/v2/openapi"
    }
  ],
  "paths": {
    "/task/{task_id}": {
      "get": {
        "summary": "use the task_id created by createTask to get the status of a task",
        "operationId": "getTask",
        "parameters": [
          {
            "name": "task_id",
            "in": "path",
            "required": true,
            "schema": {
              "type": "string"
            }
          }
        ],
        "responses": {
          "200": {
            "description": "succeed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/SuccessResponse"
                }
              }
            }
          },
          "400": {
            "description": "failed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          }
        }
      }
    },
    "/upload": {
      "post": {
        "summary": "upload a file",
        "operationId": "uploadFile",
        "requestBody": {
          "content": {
            "multipart/form-data": {
              "schema": {
                "type": "object",
                "properties": {
                  "file": {
                    "type": "string",
                    "format": "binary"
                  }
                },
                "required": [
                  "file"
                ]
              },
              "encoding": {
                "profileImage": {
                  "contentType": "image/png, image/jpeg"
                }
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "succeed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/SuccessResponse"
                }
              }
            }
          },
          "400": {
            "description": "failed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          }
        }
      }
    },
    "/upload/sts/token": {
      "post": {
        "summary": "get a sts token",
        "operationId": "getStsToken",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "type": "object",
                "properties": {
                  "format": {
                    "$ref": "#/components/schemas/ImageFormat"
                  }
                },
                "required": [
                  "format"
                ]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "succeed",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "code": {
                      "type": "integer",
                      "enum": [
                        0
                      ]
                    },
                    "data": {
                      "$ref": "#/components/schemas/StsTokenResponse"
                    }
                  },
                  "required": [
                    "code",
                    "data"
                  ]
                }
              }
            }
          },
          "400": {
            "description": "failed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          },
          "403": {
            "description": "failed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          }
        }
      }
    },
    "/task": {
      "post": {
        "summary": "create a task",
        "operationId": "createTask",
        "requestBody": {
          "content": {
            "application/json": {
              "schema": {
                "oneOf": [
                  {
                    "$ref": "#/components/schemas/TextToModelRequest"
                  },
                  {
                    "$ref": "#/components/schemas/ImageToModelRequest"
                  },
                  {
                    "$ref": "#/components/schemas/MultiviewToModelRequest"
                  },
                  {
                    "$ref": "#/components/schemas/TextureModelRequest"
                  },
                  {
                    "$ref": "#/components/schemas/RefineModelRequest"
                  },
                  {
                    "$ref": "#/components/schemas/AnimatePrerigcheckRequest"
                  },
                  {
                    "$ref": "#/components/schemas/AnimateRigRequest"
                  },
                  {
                    "$ref": "#/components/schemas/AnimateRetargetRequest"
                  },
                  {
                    "$ref": "#/components/schemas/StylizeModelRequest"
                  },
                  {
                    "$ref": "#/components/schemas/ConvertModelRequest"
                  }
                ]
              }
            }
          }
        },
        "responses": {
          "200": {
            "description": "succeed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/SuccessTask"
                }
              }
            }
          },
          "400": {
            "description": "failed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          }
        }
      }
    },
    "/user/balance": {
      "get": {
        "summary": "get user balance",
        "operationId": "getBalance",
        "responses": {
          "200": {
            "description": "succeed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/SuccessResponse"
                }
              }
            }
          },
          "500": {
            "description": "failed",
            "content": {
              "application/json": {
                "schema": {
                  "$ref": "#/components/schemas/ErrorResponse"
                }
              }
            }
          }
        }
      }
    }
  },
  "components": {
    "schemas": {
      "SuccessResponse": {
        "type": "object",
        "properties": {
          "code": {
            "type": "integer",
            "enum": [
              0
            ]
          },
          "data": {
            "type": "object"
          }
        },
        "required": [
          "code",
          "data"
        ]
      },
      "ErrorResponse": {
        "type": "object",
        "properties": {
          "code": {
            "type": "integer"
          },
          "message": {
            "type": "string"
          },
          "suggestion": {
            "type": "string"
          }
        },
        "required": [
          "code",
          "message",
          "suggestion"
        ]
      },
      "ImageFormat": {
        "type": "string",
        "enum": [
          "webp",
          "jpeg",
          "png"
        ]
      },
      "RigType": {
        "type": "string",
        "enum": [
          "biped",
          "quadruped",
          "hexapod",
          "octopod",
          "avian",
          "serpentine",
          "aquatic"
        ]
      },
      "AnimationType": {
        "type": "string",
        "enum": [
          "preset:idle",
          "preset:walk",  
          "preset:run",
          "preset:dive",
          "preset:climb",
          "preset:jump",
          "preset:slash",
          "preset:shoot",
          "preset:hurt",
          "preset:fall",
          "preset:turn",
          "preset:quadruped:walk",
          "preset:hexapod:walk",
          "preset:octopod:walk",
          "preset:serpentine:march",
          "preset:aquatic:march"
        ]
      },
      "StsTokenResponse": {
        "type": "object",
        "properties": {
          "s3_host": {
            "type": "string"
          },
          "resource_bucket": {
            "type": "string"
          },
          "resource_uri": {
            "type": "string"
          },
          "session_token": {
            "type": "string"
          },
          "sts_ak": {
            "type": "string"
          },
          "sts_sk": {
            "type": "string"
          }
        },
        "required": [
          "s3_host",
          "resource_bucket",
          "resource_uri",
          "session_token",
          "sts_ak",
          "sts_sk"
        ]
      },
      "ModelVersion": {
        "type": "string",
        "enum": [
          "Turbo-v1.0-20250506",
          "v2.5-20250123",
          "v2.0-20240919",
          "v1.4-20240625"
        ],
        "default": "default"
      },
      "StandardModelVersion": {
        "type": "string",
        "enum": [
          "v2.5-20250123",
          "v2.0-20240919",
          "v1.4-20240625"
        ],
        "default": "default"
      },
      "TexturePrompt": {
        "type": "object",
        "properties": {
          "text": {
            "type": "string"
          },
          "image": {
            "$ref": "#/components/schemas/File"
          },
          "style_image": {
            "$ref": "#/components/schemas/File"
          }
        }
      },
      "TextureParams": {
        "type": "object",
        "properties": {
          "texture": {
            "type": "boolean",
            "default": true
          },
          "pbr": {
            "type": "boolean",
            "default": true
          },
          "texture_quality": {
            "type": "string",
            "enum": [
              "standard",
              "detailed"
            ],
            "default": "standard"
          },
          "texture_alignment": {
            "type": "string",
            "enum": [
              "original_image",
              "geometry"
            ],
            "default": "original_image"
          }
        }
      },
      "BaseModelParams": {
        "type": "object",
        "properties": {
          "model_version": {
            "$ref": "#/components/schemas/ModelVersion"
          },
          "face_limit": {
            "type": "integer"
          },
          "auto_size": {
            "type": "boolean",
            "default": false
          },
          "quad": {
            "type": "boolean",
            "default": false
          }
        }
      },
      "TextToModelRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "text_to_model"
            ]
          },
          "prompt": {
            "type": "string",
            "maxLength": 1024
          },
          "negative_prompt": {
            "type": "string",
            "maxLength": 1024
          },
          "text_seed": {
            "type": "integer"
          },
          "model_seed": {
            "type": "integer"
          },
          "texture_seed": {
            "type": "integer"
          },
          "style": {
            "type": "string",
            "enum": [
              "person:person2cartoon",
              "animal:venom",
              "object:clay",
              "object:steampunk",
              "object:christmas",
              "object:barbie",
              "gold",
              "ancient_bronze"
            ]
          }
        },
        "allOf": [
          {
            "$ref": "#/components/schemas/BaseModelParams"
          },
          {
            "$ref": "#/components/schemas/TextureParams"
          }
        ],
        "required": [
          "type",
          "prompt"
        ]
      },
      "ImageToModelRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "image_to_model"
            ]
          },
          "file": {
            "$ref": "#/components/schemas/File"
          },
          "model_seed": {
            "type": "integer"
          },
          "texture_seed": {
            "type": "integer"
          },
          "style": {
            "type": "string",
            "enum": [
              "person:person2cartoon",
              "animal:venom",
              "object:clay",
              "object:steampunk",
              "object:christmas",
              "object:barbie",
              "gold",
              "ancient_bronze"
            ]
          },
          "orientation": {
            "type": "string",
            "enum": [
              "align_image",
              "default"
            ],
            "default": "default"
          },
          "smart_low_poly": {
            "type": "boolean",
            "default": false
          },
          "generate_parts": {
            "type": "boolean",
            "default": false
          }
        },
        "allOf": [
          {
            "$ref": "#/components/schemas/BaseModelParams"
          },
          {
            "$ref": "#/components/schemas/TextureParams"
          }
        ],
        "required": [
          "type",
          "file"
        ]
      },
      "MultiviewToModelRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "multiview_to_model"
            ]
          },
          "files": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/File"
            }
          },
          "mode": {
            "type": "string",
            "enum": [
              "LEFT",
              "RIGHT"
            ]
          },
          "orthographic_projection": {
            "type": "boolean",
            "default": false
          },
          "model_version": {
            "$ref": "#/components/schemas/StandardModelVersion"
          },
          "model_seed": {
            "type": "integer"
          },
          "texture_seed": {
            "type": "integer"
          },
          "style": {
            "type": "string",
            "enum": [
              "person:person2cartoon",
              "animal:venom",
              "object:clay",
              "object:steampunk",
              "object:christmas",
              "object:barbie",
              "gold",
              "ancient_bronze"
            ]
          },
          "orientation": {
            "type": "string",
            "enum": [
              "align_image",
              "default"
            ],
            "default": "default"
          }
        },
        "allOf": [
          {
            "$ref": "#/components/schemas/BaseModelParams"
          },
          {
            "$ref": "#/components/schemas/TextureParams"
          }
        ],
        "required": [
          "type",
          "files"
        ]
      },
      "TextureModelRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "texture_model"
            ]
          },
          "model_seed": {
            "type": "integer"
          },
          "texture_seed": {
            "type": "integer"
          },
          "original_model_task_id": {
            "type": "string"
          },
          "compress": {
            "$ref": "#/components/schemas/CompressType"
          },
          "model_version": {
            "type": "string",
            "enum": [
              "v2.5-20250123",
              "v2.0-20240919"
            ],
            "default": "v2.5-20250123"
          },
          "part_names": {
            "type": "array",
            "items": {
              "type": "string"
            }
          },
          "bake": {
            "type": "boolean",
            "default": true
          },
          "texture_prompt": {
            "$ref": "#/components/schemas/TexturePrompt"
          },
        },
        "allOf": [
          {
            "$ref": "#/components/schemas/TextureParams"
          }
        ],
        "required": [
          "type",
          "original_model_task_id"
        ]
      },
      "RefineModelRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "refine_model"
            ]
          },
          "draft_model_task_id": {
            "type": "string"
          }
        },
        "required": [
          "type",
          "draft_model_task_id"
        ]
      },
      "AnimatePrerigcheckRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "animate_prerigcheck"
            ]
          },
          "original_model_task_id": {
            "type": "string"
          }
        },
        "required": [
          "type",
          "original_model_task_id"
        ]
      },
      "AnimateRigRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "animate_rig"
            ]
          },
          "original_model_task_id": {
            "type": "string"
          },
          "out_format": {
            "type": "string",
            "enum": [
              "glb",
              "fbx"
            ],
            "default": "glb"
          },
          "topology": {
            "type": "string",
            "enum": [
              "bip",
              "quad"
            ]
          },
          "spec": {
            "type": "string",
            "enum": [
              "mixamo",
              "tripo"
            ],
            "default": "tripo"
          }
        },
        "required": [
          "type",
          "original_model_task_id"
        ]
      },
      "AnimateRetargetRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "animate_retarget"
            ]
          },
          "original_model_task_id": {
            "type": "string"
          },
          "out_format": {
            "type": "string",
            "enum": [
              "glb",
              "fbx"
            ],
            "default": "glb"
          },
          "animation": {
            "$ref": "#/components/schemas/AnimationType"
          },
          "animations": {
            "type": "array",
            "items": {
              "$ref": "#/components/schemas/AnimationType"
            }
          },
          "bake_animation": {
            "type": "boolean",
            "default": true
          },
         "export_with_geometry": {
            "type": "boolean",
            "default": true
          }
        },
        "required": [
          "type",
          "original_model_task_id"
        ],
        "oneOf": [
          {
            "required": ["animation"]
          },
          {
            "required": ["animations"]
          }
        ]
      },
      "StylizeModelRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "stylize_model"
            ]
          },
          "style": {
            "type": "string",
            "enum": [
              "lego",
              "voxel",
              "voronoi",
              "minecraft"
            ]
          },
          "original_model_task_id": {
            "type": "string"
          },
          "block_size": {
            "type": "integer",
            "default": 80
          }
        },
        "required": [
          "type",
          "style",
          "original_model_task_id"
        ]
      },
      "ConvertModelRequest": {
        "type": "object",
        "properties": {
          "type": {
            "type": "string",
            "enum": [
              "convert_model"
            ]
          },
          "format": {
            "type": "string",
            "enum": [
              "GLTF",
              "USDZ",
              "FBX",
              "OBJ",
              "STL",
              "3MF"
            ]
          },
          "original_model_task_id": {
            "type": "string"
          },
          "quad": {
            "type": "boolean",
            "default": false
          },
          "force_symmetry": {
            "type": "boolean",
            "default": false
          },
          "face_limit": {
            "type": "integer",
            "default": 10000
          },
          "flatten_bottom": {
            "type": "boolean",
            "default": false
          },
          "flatten_bottom_threshold": {
            "type": "number",
            "default": 0.01
          },
          "texture_size": {
            "type": "integer",
            "default": 4096
          },
          "texture_format": {
            "type": "string",
            "enum": [
              "BMP",
              "DPX",
              "HDR",
              "JPEG",
              "OPEN_EXR",
              "PNG",
              "TARGA",
              "TIFF",
              "WEBP"
            ],
            "default": "JPEG"
          },
          "pivot_to_center_bottom": {
            "type": "boolean",
            "default": false
          },
          "with_animation": {
            "type": "boolean",
            "default": false
          },
          "pack_uv": {
            "type": "boolean",
            "default": false
          },
          "bake": {
            "type": "boolean",
            "default": false
          },
          "part_names": {
            "type": "array",
            "items": {
              "type": "string"
            }
          }
        },
        "required": [
          "type",
          "format",
          "original_model_task_id"
        ]
      },
      "Task": {
        "type": "object",
        "properties": {
          "task_id": {
            "type": "string"
          },
          "type": {
            "type": "string"
          },
          "status": {
            "type": "string",
            "enum": [
              "queued",
              "running",
              "success",
              "failed",
              "cancelled",
              "unknown",
              "banned",
              "expired"
            ]
          },
          "input": {
            "type": "object"
          },
          "output": {
            "type": "object",
            "properties": {
              "model": {
                "type": "string"
              },
              "base_model": {
                "type": "string"
              },
              "pbr_model": {
                "type": "string"
              },
              "rendered_image": {
                "type": "string"
              },
              "riggable": {
                "type": "boolean"
              },
              "rig_type": {
                "type": "string"
              },
              "topology": {
                "type": "string",
                "enum": [
                  "bip",
                  "quad"
                ]
              }
            }
          },
          "progress": {
            "type": "integer",
            "minimum": 0,
            "maximum": 100
          },
          "error_code": {
            "type": "integer"
          },
          "error_msg": {
            "type": "string"
          },
          "create_time": {
            "type": "integer"
          },
          "running_left_time": {
            "type": "integer"
          },
          "queuing_num": {
            "type": "integer"
          }
        },
        "required": [
          "task_id",
          "type",
          "status",
          "input",
          "output",
          "progress",
          "create_time"
        ]
      },
      "SuccessTask": {
        "type": "object",
        "properties": {
          "code": {
            "type": "integer",
            "enum": [
              0
            ]
          },
          "data": {
            "type": "object",
            "properties": {
              "task_id": {
                "description": "used for getTask",
                "type": "string"
              }
            },
            "required": [
              "task_id"
            ]
          }
        },
        "required": [
          "code",
          "data"
        ]
      },
      "Balance": {
        "type": "object",
        "properties": {
          "balance": {
            "type": "number"
          },
          "frozen": {
            "type": "number"
          }
        },
        "required": [
          "balance",
          "frozen"
        ]
      },
      "File": {
        "type": "object",
        "required": [
          "type"
        ],
        "properties": {
          "type": {
            "type": "string"
          }
        },
        "oneOf": [
          {
            "required": [
              "file_token"
            ],
            "properties": {
              "file_token": {
                "type": "string"
              }
            }
          },
          {
            "required": [
              "url"
            ],
            "properties": {
              "url": {
                "type": "string"
              }
            }
          },
          {
            "required": [
              "object"
            ],
            "properties": {
              "object": {
                "type": "object",
                "required": [
                  "bucket",
                  "key"
                ],
                "properties": {
                  "bucket": {
                    "type": "string"
                  },
                  "key": {
                    "type": "string"
                  }
                }
              }
            }
          }
        ]
      }
    }
  }
}