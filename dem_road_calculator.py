# -*- coding: utf-8 -*-
"""
/***************************************************************************
 DemRoadCalculator
                                 A QGIS plugin
 Calculate slope and aspect road lines using DEM
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2024-08-03
        git sha              : $Format:%H$
        copyright            : (C) 2024 by Dmitry D.
        email                : dmitrdobr@mail.ru
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, pyqtSignal, pyqtSlot, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import (
    Qgis,
    QgsVector,
    QgsProject, 
    QgsVectorLayer, 
    QgsRasterLayer,
    QgsMapLayer,
    QgsGeometry,
    QgsFeature, 
    QgsFeatureIterator, 
    QgsPointXY, 
    QgsTask,
    QgsField,
    QgsFields,
    QgsCoordinateTransform,
    QgsCoordinateTransformContext,
    QgsReferencedGeometryBase,
    QgsCoordinateReferenceSystem,
    QgsTaskManager,
    edit
)

# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .dem_road_calculator_dialog import DemRoadCalculatorDialog
import os.path

import math
from .calculations import functionList, _3x3WindowMatrix, _WGHT

VERSION = Qgis.QGIS_VERSION
MESSAGE_CATEGORY = "RoadTask"
TASK_DESCRIPTION = "ROAD_DEM_CALCULATION"

class CalculationData(): # DataClass for calculation params
    def __init__(self, rasterLayer, vectorLayer, bandNo, fields, step = 100, roundval = 2, algorytm = 0):
        self.DemRasterLayer = rasterLayer
        self.LineRoadsLayer = vectorLayer
        self.RasterChannel = bandNo
        self.VectorFields = fields # dict with _hgt, _slope, _aspect fields names
        # e.g.
        # ('_aspect' : '123')
        # ('_hgt' : '123')
        # ('_slope' : '123')
        self.SampleStep = step
        self.RoundValue = roundval
        self.AlgoritmId = algorytm

        ####
        self.transformer = QgsCoordinateTransform(self.LineRoadsLayer.crs(), self.DemRasterLayer.crs(), QgsProject.instance())

        self.GradientsFunction = functionList[algorytm]

    def __str__(self):
        str_r = "Calculation Parameters\n"
        str_r += "Lines Layer: " + self.LineRoadsLayer.name() + "\n"
        str_r += "DEM Layer: " + self.DemRasterLayer.name() + " Band:" + str(self.RasterChannel) + "\n"
        str_r += "Sample Step: " + str(self.SampleStep) + " in " + str(self.DemRasterLayer.crs().mapUnits())  + "\n"
        str_r += "Algorytm_id: " + str(self.AlgoritmId)
        return str_r
    
    def checkCrs(self):
        pass

    def getWindowMatrixAtPoint(self, point):
        # point from line layer crs in DEM layer src
        rasterX = self.DemRasterLayer.rasterUnitsPerPixelX()
        rasterY = self.DemRasterLayer.rasterUnitsPerPixelY()

        transformedPoint = self.transformer.transform(point) # slight window matrix 
        
        SlWindowMatrix = [[0] * 3 for _ in range(3)] 
        for y in range(-1,2):
            for x in range(-1,2):
                buf_point = QgsPointXY(transformedPoint) # буферная точка
                buf_point += QgsVector(rasterX*x, -rasterY*y) # смещение точки для заполнения матрицы
                val, res = self.DemRasterLayer.dataProvider().sample(buf_point , self.RasterChannel)

                SlWindowMatrix[y+1][x+1] = val if res else None
        
        return SlWindowMatrix

    def renderValuesAtPoint(self, point): # get values from DEM with given QgsPoint
        result = dict()

        transformedPoint = self.transformer.transform(point)
        val, res = self.DemRasterLayer.dataProvider().sample(transformedPoint , self.RasterChannel)
        
        matrix = self.getWindowMatrixAtPoint(point) # matrix with raster values
        matrix = _3x3WindowMatrix(matrix)

        # rendered value and bool flag of correct result

        if (self.VectorFields.get('_hgt')):
            result[self.VectorFields['_hgt']] = val if res else -999

        if (self.VectorFields.get('_slope')):
            fx, fy = self.GradientsFunction(matrix, self.DemRasterLayer.rasterUnitsPerPixelX())
            SlopeVal = math.atan(math.sqrt(pow(fx,2) + pow(fy,2))) * 57.29578
            result[self.VectorFields['_slope']] = round(SlopeVal, self.RoundValue)

        if (self.VectorFields.get('_aspect')):
            fx, fy = _WGHT(matrix)
            AspectVal = (180/math.pi) * math.atan2(fy, -fx)

            if AspectVal < 0:
                AspectVal = 90.0 - AspectVal
            elif AspectVal > 90.0:
                AspectVal = 360.0 - AspectVal + 90.0
            else:
                AspectVal = 90.0 - AspectVal


            result[self.VectorFields['_aspect']] = round(AspectVal, self.RoundValue)
        
        return dict(sorted(result.items()))
        
    def checkData(self):
        flag = True
        if (self.LineRoadsLayer.featureCount() < 0):
            print("* [Input Data Error]: line features count = 0")
            flag = False
        
        if (self.DemRasterLayer.crs().mapUnits() != Qgis.DistanceUnit.Meters):
            print("* [Input Data Error]: Dem Raster CRS must be in meters")
            flag = False

        return flag

class LineWrapper(): # wrapper for line geometry
    def __init__(self, lineGeometry):
        self.LineGeometry = None # reference to original QgsGeometry
        self.Multiline = False # object is MultiPolyLine or not
        self.isValid = True # object is valid
        try:
            self.LineGeometry = lineGeometry.asMultiPolyline()
        except TypeError:
            try:
                self.LineGeometry = lineGeometry.asPolyline()
            except TypeError:
                self.isValid = False
        else:
            self.Multiline = True

        self.currentIndexPoint = -1 # current Id of original point of geometry
        self.currentIndexPart = 0 # current Id of part of MultiPolyLine
        self.currentVector = None # current vector on which need to find new point
        self.currentPoint = None # current point from which need to find new point on given currentvector

        self.currentsegment = list()
    
    def nextPointOnGeometryAt(self, meters): # next point from current on line with given value of meters
        if (not self.currentPoint):
            self.nextPart()
            return True
        
        self.currentsegment.clear()
        self.currentsegment.append(self.currentPoint)

        if (self.Multiline): # QgsMultiPolyLine
            newPoint = None
            toAdd = meters 
            flag = False

            while meters > 0:
                if (flag):
                    toAdd = meters
                    if (not self.nextPart()):
                        self.currentPoint = self.LineGeometry[self.currentIndexPart][self.currentIndexPoint + 1]
                        self.currentsegment.append(self.currentPoint)
                        return False
                    self.currentsegment.append(self.currentPoint)
                    
                meters = meters - self.currentVector.length()
                flag = True

            newPoint = self.currentPoint + self.currentVector.normalized() * toAdd
            self.currentVector = self.LineGeometry[self.currentIndexPart][self.currentIndexPoint + 1] - newPoint # new vector is next point of original geom - current calculated point
            self.currentPoint = newPoint
            self.currentsegment.append(self.currentPoint)

            return True

        else: # QgsPolyLine
            newPoint = None
            toAdd = meters 
            flag = False

            while meters > 0:
                if (flag):
                    toAdd = meters
                    if (not self.nextPart()):
                        self.currentPoint = self.LineGeometry[self.currentIndexPoint + 1]
                        self.currentsegment.append(self.currentPoint)
                        return False
                    self.currentsegment.append(self.currentPoint)
                    
                meters = meters - self.currentVector.length()
                flag = True

            newPoint = self.currentPoint + self.currentVector.normalized() * toAdd
            self.currentVector = self.LineGeometry[self.currentIndexPoint + 1] - newPoint # new vector is next point of original geom - current calculated point
            self.currentPoint = newPoint
            self.currentsegment.append(self.currentPoint)

            return True
            
    def getCurrentPoint(self): # current calculated point
        return self.currentPoint 
    
    def getCurrentSegment(self): # current found segment 
        # currentLineSegment = QgsGeometry.fromPolylineXY(self.currentsegment)
        # return currentLineSegment
        segment = self.currentsegment.copy()
        return segment
            
    def nextPart(self): # next part of line geometry
        if (self.Multiline): # QgsMultiPolyLine
            if (self.currentIndexPoint + 2 < len(self.LineGeometry[self.currentIndexPart])): # if not the last pair of points in current polyline
                self.currentIndexPoint += 1
            elif (self.currentIndexPart + 1 < len(self.LineGeometry)): # try to access next polyline
                self.currentIndexPart += 1
                self.currentIndexPoint = 0
            else:
                return False

            self.currentPoint = self.LineGeometry[self.currentIndexPart][self.currentIndexPoint] # reset current point for calculations
            self.currentVector = self.LineGeometry[self.currentIndexPart][self.currentIndexPoint + 1] - self.currentPoint # set current vector for nextPoint calculation

            return True
            
        else: # QgsPolyLine
            if (self.currentIndexPoint + 2 < len(self.LineGeometry)): # if not the last pair of points
                self.currentIndexPoint += 1
                self.currentPoint = self.LineGeometry[self.currentIndexPoint] # reset current point for calculations
                self.currentVector = self.LineGeometry[self.currentIndexPoint + 1] - self.currentPoint # set current vector for nextPoint calculation
                return True
            else:
                return False
    
    def reset(self): # reset wrapper
        self.currentIndexPoint = -1 # current Id of original point of geometry
        self.currentIndexPart = 0 # current Id of part of MultiPolyLine
        self.currentVector = None # current vector on which need to find new point
        self.currentPoint = None # current point from which need to find new point on given currentvector


class VectorBuilderV1(QgsTask): # Task for building points in given layer
    printres = pyqtSignal(str)

    def __init__(self, description, pointLayer, points_list, args_dict):
        super().__init__(description, QgsTask.CanCancel)
        self.pointVl = pointLayer

        self.pointsToAdd = points_list
        self.argsToAdd = args_dict

    def run(self):
        pointFeatures = []

        for i in range(0, len(self.pointsToAdd)):
            feature = QgsFeature()
            feature.setGeometry( QgsGeometry.fromPointXY(self.pointsToAdd[i]) )

            feature.setFields(self.pointVl.dataProvider().fields())

            for key, value in self.argsToAdd[i].items():
                feature.setAttribute(key, value)

            pointFeatures.append(feature)

        self.pointVl.startEditing()
        self.pointVl.dataProvider().addFeatures(pointFeatures)
        self.pointVl.commitChanges()

        self.setProgress(100)

        return True
    
    def finished(self, result):
        
        self.printres.emit('* [VectorBuilder] Task Finished with ' + str(result))
        self.result = result
    
    def cancel(self):
        print('* [VectorBuilder] Task cancel')
        self.printres.emit('* [VectorBuilder] Task cancel')
        super().cancel()

class VectorBuilderV2(QgsTask): # Task for building lines in given layer
    printres = pyqtSignal(str)

    def __init__(self, description, lineLayer, lines_list, args_dict):
        super().__init__(description, QgsTask.CanCancel)
        self.lineVl = lineLayer

        self.linestoAdd = lines_list # list[ list[QgsPointXY,QgsPointXY,...], list[...] , ... ]
        self.argsToAdd = args_dict

    def run(self):
        lineFeatures = []

        for i in range(1, len(self.linestoAdd)):

            lineFeature = QgsFeature()
            lineFeature.setGeometry(QgsGeometry.fromPolylineXY(self.linestoAdd[i])) # list[QgsPointXY,QgsPointXY,...]
            lineFeature.setFields(self.lineVl.dataProvider().fields())
            
            # start point DEM values
            for key, value in self.argsToAdd[i-1].items():
                cur_key = key + "_start"
                lineFeature.setAttribute(cur_key, value)
            # end point DEM values
            for key, value in self.argsToAdd[i].items():
                cur_key = key + "_end"
                lineFeature.setAttribute(cur_key, value)

            lineFeatures.append(lineFeature)

        self.lineVl.startEditing()
        self.lineVl.dataProvider().addFeatures(lineFeatures)
        self.lineVl.commitChanges()
 
        self.setProgress(100)

        return True
    
    def finished(self, result):
        self.printres.emit('* [VectorBuilderV2] Task Finished with ' + str(result))
        self.result = result
    
    def cancel(self):
        print('* [VectorBuilder] Task cancel')
        self.printres.emit('* [VectorBuilder] Task cancel')
        super().cancel()

class CalculateTask(QgsTask): # main calculation task
    initBuliderTaskV1 = pyqtSignal(list , list) # points + values
    initBuliderTaskV2 = pyqtSignal(list , list) # lines + values
    printres = pyqtSignal(str)

    def __init__(self, description, wrappedlines, options):
        super().__init__(description, QgsTask.CanCancel)
        self.wrappedLinesList = wrappedlines
        self.taskOptions = options

        self.result = None

    def run(self): # основная функция задачи  
        print('** Task run')

        step = 100 / len(self.wrappedLinesList)
        current_progress = 0.0

        for feature in self.wrappedLinesList:
            if self.isCanceled():
                return False
            
            if (not feature.isValid):
                self.printres.emit("* Not valid feature")
                continue
            
            point_list = []
            arg_list = []
            line_list = []

            while(feature.nextPointOnGeometryAt(100)):
                point_list.append(feature.getCurrentPoint())
                arg_list.append(self.taskOptions.renderValuesAtPoint(feature.getCurrentPoint()))
                line_list.append(feature.getCurrentSegment())
            
            point_list.append(feature.getCurrentPoint())
            arg_list.append(self.taskOptions.renderValuesAtPoint(feature.getCurrentPoint()))
            line_list.append(feature.getCurrentSegment())

            
            self.initBuliderTaskV1.emit(point_list, arg_list)
            # list of separate QgsPoints with step, list of DEM values
            self.initBuliderTaskV2.emit(line_list, arg_list)
            # list of QgsPoints for lines, list of DEM values

            # UPDATE PROGRESS
            current_progress += step
            self.setProgress(round(current_progress))

        return True
    
    def finished(self, result):
        print('* [CalculateTask] Task Finished with ' + str(result))
        self.printres.emit('* [CalculateTask] Task Ended with ' + str(result))
        self.result = result
       
    def cancel(self): # отмена задачи
        print('* [CalculateTask] Task cancel')
        self.printres.emit('* [CalculateTask] Task cancel')
        super().cancel()



class DemRoadCalculator:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'DemRoadCalculator_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Dem Road Calculator')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None

        self.task_manager = QgsTaskManager()  
        self.task_manager.allTasksFinished.connect(self.allTasksFinished)
        self.task_manager.progressChanged.connect(self.taskProgresChanged)

        self.active_task = None
        self.iterator = 0

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('DemRoadCalculator', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/dem_road_calculator/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'Dem Road Calculator'),
            callback=self.run,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.first_start = True


    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Dem Road Calculator'),
                action)
            self.iface.removeToolBarIcon(action)


    def run(self):
        """Run method that performs all the real work"""

        # Create the dialog with elements (after translation) and keep reference
        # Only create GUI ONCE in callback, so that it will only load when the plugin is started
        if self.first_start == True:
            self.first_start = False
            self.dlg = DemRoadCalculatorDialog()

            self.dlg.pushButton_start.clicked.connect(self.runTask)
            #self.dlg.pushButton_stop.clicked.connect(self.stopTask)

        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass

    def WrapLines(self, vector_layer):
        lines_list = []
        for geom in vector_layer.getFeatures():
            wrapper = LineWrapper(geom.geometry())
            # print(wrapper.LineGeometry)

            lines_list.append(wrapper)

        return lines_list

    def runTask(self):
        self.dlg.progressBar.setValue(0)
        self.dlg.setGUIEnabled(False)

        options = self.dlg.getTaskOptions()
        data = CalculationData(options[1],options[0],options[2],options[6],options[3],options[5],options[4])

        if not data.checkData():
            return

        self.vectorLayer = QgsVectorLayer("Point", "temporary_points", "memory") # create temporary layer
        self.vectorLayer.setCrs(self.dlg.mMapLayerComboBox_lines.currentLayer().crs())

        self.linesLayer = QgsVectorLayer("LineString", "temporary_lines", "memory") # create temporary layer
        self.linesLayer.setCrs(self.dlg.mMapLayerComboBox_lines.currentLayer().crs())

        for value in list(sorted(options[6].values())):
            self.vectorLayer.dataProvider().addAttributes( [QgsField(value,  QVariant.Double) ] ) # add attributes to point layer

            self.linesLayer.dataProvider().addAttributes( [QgsField(value + "_start",  QVariant.Double) ] )  # add attributes to line layer
            self.linesLayer.dataProvider().addAttributes( [QgsField(value + "_end",  QVariant.Double) ] )
        
        self.vectorLayer.updateFields()
        self.linesLayer.updateFields()

        QgsProject.instance().addMapLayer(self.vectorLayer)
        QgsProject.instance().addMapLayer(self.linesLayer)

        
        lines_list = self.WrapLines(self.dlg.mMapLayerComboBox_lines.currentLayer()) # Wrap Line geometry

        
        self.active_task = CalculateTask(TASK_DESCRIPTION,lines_list,data) # start new task
        self.task_manager.addTask(self.active_task)

        self.active_task.initBuliderTaskV1.connect(self.runVectorEditTaskV1)
        self.active_task.initBuliderTaskV2.connect(self.runVectorEditTaskV2)

        self.active_task.printres.connect(self.printRes)

        self.printRes(" * start")


    def runVectorEditTaskV1(self, array, array_args):
        task = VectorBuilderV1(TASK_DESCRIPTION, pointLayer=self.vectorLayer,
                                points_list=array, args_dict=array_args) 
        # pointLayer to create, point list with point coords, calculated values for points
        task.printres.connect(self.printRes)
        self.task_manager.addTask(task)

    def runVectorEditTaskV2(self, array_lines, array_args):
        task = VectorBuilderV2(TASK_DESCRIPTION, lineLayer=self.linesLayer,
                                lines_list=array_lines, args_dict=array_args) 
        # lineLayer to create, lines list with point coords, calculated values for points
        task.printres.connect(self.printRes)
        self.task_manager.addTask(task)


    def allTasksFinished(self):
        self.printRes(" * [Task Manager]: ALL TASKS FINISED")
        self.dlg.setGUIEnabled(True)
        self.iface.messageBar().pushMessage("Task finished", "Output layers generated", level=Qgis.Success, duration=10)
        
    
    def taskProgresChanged(self, task_id, progress): # прогресс в задаче обновлен
        # print(task_id, progress)
        self.dlg.progressBar.setValue(int(progress))

    def printRes(self, string):
        print('[',self.iterator,']' , string)
        self.iterator += 1

    def printDebug(self):
        for i, task in enumerate(self.task_manager.tasks()):
            self.printRes("Task No " + str(i) + " result is " + str(task.result))
            self.printRes("Task No " + str(i) + "  isActive " + str(task.isActive()))
            self.printRes("Task No " + str(i) + "  status " + str(task.status()))
            print(task)
            del task
        pass

