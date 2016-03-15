/* Copyright 2015,2016 Canonical Ltd.  This software is licensed under the
 * GNU Affero General Public License version 3 (see the file LICENSE).
 *
 * MAAS Space Details Controller
 */

angular.module('MAAS').controller('SpaceDetailsController', [
    '$scope', '$rootScope', '$routeParams', '$filter', '$location',
    'SpacesManager', 'VLANsManager', 'SubnetsManager', 'FabricsManager',
    'UsersManager', 'ManagerHelperService', 'ErrorService',
    function(
        $scope, $rootScope, $routeParams, $filter, $location,
        SpacesManager, VLANsManager, SubnetsManager, FabricsManager,
        UsersManager, ManagerHelperService, ErrorService) {

        // Set title and page.
        $rootScope.title = "Loading...";

        // Note: this value must match the top-level tab, in order for
        // highlighting to occur properly.
        $rootScope.page = "spaces";

        // Initial values.
        $scope.loaded = false;
        $scope.space = null;
        $scope.subnets = null;

        // Updates the page title.
        function updateTitle() {
            $rootScope.title = $scope.space.name;
        }

        // Called when the space has been loaded.
        function spaceLoaded(space) {
            $scope.space = space;
            $scope.loaded = true;
            $scope.subnets = SpacesManager.getSubnets($scope.space);

            updateTitle();
            updateSubnetTable();
        }

        // Generate a table that can easily be rendered in the view.
        function updateSubnetTable() {
            var rows = [];
            var subnets = $filter('orderBy')($scope.subnets, ['name']);
            angular.forEach(subnets, function(subnet) {
                var vlan = VLANsManager.getItemFromList(
                    subnet.vlan);
                var fabric = FabricsManager.getItemFromList(
                    vlan.fabric);
                var row = {
                    vlan: vlan,
                    vlan_name: VLANsManager.getName(vlan),
                    subnet: subnet,
                    subnet_name: SubnetsManager.getName(subnet),
                    fabric: fabric,
                    fabric_name: fabric.name
                };
                rows.push(row);
            });
            $scope.rows = rows;
        }


        // Return true if the authenticated user is super user.
        $scope.isSuperUser = function() {
            return UsersManager.isSuperUser();
        };

        // Return true if this is the default Space
        $scope.isDefaultSpace = function() {
            if(!angular.isObject($scope.space)) {
                return false;
            }
            return $scope.space.id === 0;
        };

        // Called when the delete space button is pressed.
        $scope.deleteButton = function() {
            $scope.confirmingDelete = true;
        };

        // Called when the cancel delete space button is pressed.
        $scope.cancelDeleteButton = function() {
            $scope.confirmingDelete = false;
        };

        // Convert the Python dict error message to displayed message.
        // We know it's probably a form ValidationError dictionary, so just use
        // it as such, and recover if that doesn't parse as JSON.
        $scope.convertPythonDictToErrorMsg = function(pythonError) {
            var dictionary;
            try {
                dictionary = JSON.parse(pythonError);
            } catch(e) {
                if(e instanceof SyntaxError) {
                    return pythonError;
                } else {
                    throw e;
                }
            }
            var result = '', msg = '';
            var key;
            angular.forEach(dictionary, function(value, key) {
                result += key + ":  ";
                angular.forEach(dictionary[key], function(value) {
                        result += value + "  ";
                });
            });
            return result;
        };

        // Called when the confirm delete space button is pressed.
        $scope.deleteConfirmButton = function() {
            SpacesManager.deleteSpace($scope.space).then(function() {
                $scope.confirmingDelete = false;
                $location.path("/spaces");
            }, function(error) {
                $scope.error = $scope.convertPythonDictToErrorMsg(error);
            });
        };

        // Load all the required managers.
        ManagerHelperService.loadManagers([
            SpacesManager, SubnetsManager, SubnetsManager, FabricsManager,
            UsersManager]).then(function() {
            // Possibly redirected from another controller that already had
            // this space set to active. Only call setActiveItem if not
            // already the activeItem.
            var activeSpace = SpacesManager.getActiveItem();
            var requestedSpace = parseInt($routeParams.space_id, 10);
            if(isNaN(requestedSpace)) {
                ErrorService.raiseError("Invalid space identifier.");
            } else if(angular.isObject(activeSpace) &&
                activeSpace.id === requestedSpace) {
                spaceLoaded(activeSpace);
            } else {
                SpacesManager.setActiveItem(
                    requestedSpace).then(function(space) {
                        spaceLoaded(space);
                    }, function(error) {
                        ErrorService.raiseError(error);
                    });
            }
        });
    }]);