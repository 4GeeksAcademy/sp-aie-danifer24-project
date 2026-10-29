import type { Config } from "jest";

const config: Config = {
  rootDir: "../..",
  preset: "<rootDir>/uis/backoffice/node_modules/ts-jest",
  testEnvironment: "<rootDir>/uis/backoffice/node_modules/jest-environment-jsdom",
  testMatch: ["<rootDir>/uis/backoffice/tests/**/*.test.ts"],
  collectCoverageFrom: [
    "<rootDir>/uis/backoffice/lib/auth.ts",
    "<rootDir>/uis/backoffice/lib/passwords.ts",
    "<rootDir>/uis/backoffice/lib/account.ts",
    "<rootDir>/packages/shared/auth/session.ts",
  ],
  coveragePathIgnorePatterns: ["/node_modules/", "/coverage/"],
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/uis/backoffice/$1",
  },
  transform: {
    "^.+\\.tsx?$": ["<rootDir>/uis/backoffice/node_modules/ts-jest", { tsconfig: "<rootDir>/uis/backoffice/tsconfig.json" }],
  },
  clearMocks: true,
  coverageReporters: ["text", "lcov", "json"],
};

export default config;
