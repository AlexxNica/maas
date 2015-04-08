/* Copyright 2015 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * Unit tests for ValidationService.
 */

describe("ValidationService", function() {

    // Load the MAAS module.
    beforeEach(module("MAAS"));

    // Load the ValidationService.
    var ValidationService;
    beforeEach(inject(function($injector) {
        ValidationService = $injector.get("ValidationService");
    }));

    describe("validateHostname", function() {

        var scenarios = [
            {
                input: null,
                valid: false
            },
            {
                input: "",
                valid: false
            },
            {
                input: "aB0-",
                valid: false
            },
            {
                input: "aB0-z",
                valid: true
            },
            {
                input: "aB0-z.",
                valid: false
            },
            {
                input: "abc_alpha",
                valid: false
            },
            {
                input: "abc^&alpha",
                valid: false
            },
            {
                input: "abcalpha",
                valid: true
            },
            {
                input: "aB0-z.local",
                valid: false
            },
            {
                input: "abc_alpha.local",
                valid: false
            },
            {
                input: "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz" +
                    "abcdefghijk",
                valid: true
            },
            {
                input: "abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz" +
                    "abcdefghijkl",
                valid: false
            }
        ];

        angular.forEach(scenarios, function(scenario) {
            it("validates: " + scenario.input, function() {
                var result = ValidationService.validateHostname(
                    scenario.input);
                expect(result).toBe(scenario.valid);
            });
        });
    });

    describe("validateMAC", function() {

        var scenarios = [
            {
                input: null,
                valid: false
            },
            {
                input: "",
                valid: false
            },
            {
                input: "00:",
                valid: false
            },
            {
                input: "::",
                valid: false
            },
            {
                input: "00:11:",
                valid: false
            },
            {
                input: "00:11:22:",
                valid: false
            },
            {
                input: "00:11:22:33:",
                valid: false
            },
            {
                input: "00:11:22:33:44:",
                valid: false
            },
            {
                input: "00:11:22:33:44:55",
                valid: true
            },
            {
                input: "aa:bb:cc:dd:ee:ff",
                valid: true
            },
            {
                input: "AA:BB:CC:DD:EE:00",
                valid: true
            },
            {
                input: "aa:bb:cc:dd:ee:ff:",
                valid: false
            },
            {
                input: "gg:bb:cc:zz:ee:ff",
                valid: false
            }
        ];

        angular.forEach(scenarios, function(scenario) {
            it("validates: " + scenario.input, function() {
                var result = ValidationService.validateMAC(
                    scenario.input);
                expect(result).toBe(scenario.valid);
            });
        });
    });

    describe("validateIPv4", function() {

        var scenarios = [
            {
                input: null,
                valid: false
            },
            {
                input: "",
                valid: false
            },
            {
                input: "192.168",
                valid: false
            },
            {
                input: "192.168.1",
                valid: false
            },
            {
                input: "192.168.1.1",
                valid: true
            },
            {
                input: "256.168.1.1",
                valid: false
            }
        ];

        angular.forEach(scenarios, function(scenario) {
            it("validates: " + scenario.input, function() {
                var result = ValidationService.validateIPv4(
                    scenario.input);
                expect(result).toBe(scenario.valid);
            });
        });
    });

    describe("validateIPv6", function() {

        var scenarios = [
            {
                input: null,
                valid: false
            },
            {
                input: "",
                valid: false
            },
            {
                input: "2001",
                valid: false
            },
            {
                input: "2001:",
                valid: false
            },
            {
                input: "2001:db8::1",
                valid: true
            },
            {
                input: "2001:67C:1562::16",
                valid: true
            },
            {
                input: "200001:db8::1",
                valid: false
            },
            {
                input: "2001:db008::1",
                valid: false
            },
            {
                input: "2001::db8::1",
                valid: false
            },
            {
                input: "ff00:db8::1",
                valid: false
            },
            {
                input: "fe80:db8::1",
                valid: false
            },
            {
                input: "::1",
                valid: false
            }
        ];

        angular.forEach(scenarios, function(scenario) {
            it("validates: " + scenario.input, function() {
                var result = ValidationService.validateIPv6(
                    scenario.input);
                expect(result).toBe(scenario.valid);
            });
        });
    });

    describe("validateIP", function() {

        it("returns true if validateIPv4 returns true", function() {
            spyOn(ValidationService, "validateIPv4").and.returnValue(true);
            spyOn(ValidationService, "validateIPv6").and.returnValue(false);
            expect(ValidationService.validateIP("192.168.1.1")).toBe(true);
        });

        it("returns true if validateIPv6 returns true", function() {
            spyOn(ValidationService, "validateIPv4").and.returnValue(false);
            spyOn(ValidationService, "validateIPv6").and.returnValue(true);
            expect(ValidationService.validateIP("::1")).toBe(true);
        });

        it("returns false if validateIPv4 and validateIPv6 returns false",
            function() {
                spyOn(ValidationService, "validateIPv4").and.returnValue(false);
                spyOn(ValidationService, "validateIPv6").and.returnValue(false);
                expect(ValidationService.validateIP("invalid")).toBe(false);
            });
    });

    describe("validateIPInRange", function() {

        var scenarios = [
            {
                ip: "192.168.2.1",
                range: "192.168.1.0/24",
                valid: false
            },
            {
                ip: "192.168.1.1",
                range: "192.168.1.0/24",
                valid: true
            },
            {
                ip: "192.168.1.1",
                range: "172.16.0.0/16",
                valid: false
            },
            {
                ip: "172.17.1.1",
                range: "172.16.0.0/16",
                valid: false
            },
            {
                ip: "172.16.1.1",
                range: "172.16.0.0/16",
                valid: true
            },
            {
                ip: "11.1.1.1",
                range: "10.0.0.0/8",
                valid: false
            },
            {
                ip: "10.1.1.1",
                range: "10.0.0.0/8",
                valid: true
            }
        ];

        angular.forEach(scenarios, function(scenario) {
            it("validates: " + scenario.ip + " in range: " + scenario.range,
                function() {
                    var result = ValidationService.validateIPInRange(
                        scenario.ip, scenario.range);
                    expect(result).toBe(scenario.valid);
                });
        });
    });
});