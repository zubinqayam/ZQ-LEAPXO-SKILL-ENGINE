/**
 * Skill JSON Schema
 *
 * Used for validating skill registration payloads.
 * Compatible with JSON Schema Draft-07.
 */
export const skillSchema = {
  type: "object",
  required: ["skill_id", "intent", "output_format"],
  properties: {
    skill_id: {
      type: "string",
      description: "Unique identifier for the skill"
    },
    version: {
      type: "string",
      description: "Semantic version (e.g. 1.0.0)"
    },
    intent: {
      type: "string",
      description: "Natural language description of what the skill does"
    },
    output_format: {
      type: "string",
      enum: ["text", "json", "markdown"],
      description: "Expected output format"
    },
    region_code: {
      type: "string",
      description: "ISO region/country code or GLOBAL"
    },
    security_level: {
      type: "string",
      enum: ["standard", "high", "critical"],
      description: "Required security clearance level"
    },
    signature: {
      type: "string",
      description: "ECDSA signature of the skill payload"
    },
    public_key: {
      type: "string",
      description: "Public key used to verify the skill signature"
    }
  }
};
