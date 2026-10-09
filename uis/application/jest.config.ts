import type { Config } from "jest";

const config: Config = {
  rootDir: "../..",
  preset: "<rootDir>/uis/application/node_modules/ts-jest",
  testEnvironment: "<rootDir>/uis/application/node_modules/jest-environment-jsdom",
  testMatch: ["<rootDir>/uis/application/tests/**/*.test.ts"],
  collectCoverageFrom: [
    "<rootDir>/uis/application/lib/auth.ts",
    "<rootDir>/uis/application/lib/passwords.ts",
    "<rootDir>/uis/application/lib/account.ts",
    "<rootDir>/packages/shared/auth/session.ts",
  ],
  coveragePathIgnorePatterns: ["/node_modules/", "/coverage/"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/uis/application/$1",
  },
  transform: {
    "^.+\\.tsx?$": ["<rootDir>/uis/application/node_modules/ts-jest", { tsconfig: "<rootDir>/uis/application/tsconfig.json" }],
  },
  clearMocks: true,
  coverageReporters: ["text", "lcov", "json"],
};

export default config;
