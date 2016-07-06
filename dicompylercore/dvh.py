#!/usr/bin/env python
# -*- coding: utf-8 -*-
# dvh.py
"""Class that stores dose volume histogram (DVH) data."""
# Copyright (c) 2016 Aditya Panchal
# This file is part of dicompyler-core, released under a BSD license.
#    See the file license.txt included with this distribution, also
#    available at https://github.com/dicompyler/dicompyler-core/

import numpy as np
import re
import logging
logger = logging.getLogger('dicompyler.dvh')

# Set default absolute dose and volume  units
abs_dose_units = 'gy'
abs_volume_units = 'cm3'
relative_units = '%'


class DVH:
    """Class that stores dose volume histogram (DVH) data."""

    def __init__(self, counts, bins,
                 dvh_type='cumulative',
                 dose_units=abs_dose_units,
                 volume_units=abs_volume_units,
                 rx_dose=None, name=None):
        """Initialization for a DVH from existing histogram counts and bins.

        Parameters
        ----------
        counts : iterable or numpy array
            An iterable of volume or percent count data
        bins : iterable or numpy array
            An iterable of dose bins
        dvh_type : str, optional
            Choice of 'cumulative' or 'differential' type of DVH
        dose_units : str, optional
            Absolute dose units, i.e. 'gy' or relative units '%'
        volume_units : str, optional
            Absolute volume units, i.e. 'cm3' or relative units '%'
        rx_dose : number, optional
            Prescription dose value used to normalize dose bins
        name : String, optional
            Name of the structure of the DVH
        """
        self.counts = np.array(counts)
        self.bins = np.array(bins) if bins[0] == 0 else np.append([0], bins)
        self.dvh_type = dvh_type.lower()
        self.dose_units = dose_units.lower()
        self.volume_units = volume_units.lower()
        self.rx_dose = rx_dose
        self.name = name

    @classmethod
    def from_dicom_dvh(cls, dataset, roi_num, rx_dose=None, name=None):
        """Initialization for a DVH from a pydicom RT Dose DVH sequence."""
        sequence_num = -1
        for i, d in enumerate(dataset.DVHSequence):
            if 'DVHReferencedROISequence' in d:
                if 'ReferencedROINumber' in d.DVHReferencedROISequence[0]:
                    if roi_num == \
                            d.DVHReferencedROISequence[0].ReferencedROINumber:
                        sequence_num = i
                        break
        if sequence_num == -1:
            raise AttributeError(
                "'DVHSequence' has no DVH with ROI Number '%d'." % roi_num)
        dvh = dataset.DVHSequence[sequence_num]
        data = np.array(dvh.DVHData)
        return cls(counts=data[1::2] * dvh.DVHDoseScaling,
                   bins=data[0::2].cumsum(),
                   dvh_type=dvh.DVHType,
                   dose_units=dvh.DoseUnits,
                   volume_units=dvh.DVHVolumeUnits,
                   rx_dose=None,
                   name=name)

    @classmethod
    def from_data(cls, data, binsize=1):
        """Initialization for a DVH from raw data.

        Parameters
        ----------
        data : iterable or numpy array
            An iterable of dose data that is used to create the histogram
        binsize : int, optional
            Bin width size (in cGy used to create the histogram)
        """
        data = np.array(data)
        bins = np.arange(0, data.max() + 1, binsize)
        if bins.size == 1:
            bins = np.array([0, data.max()])
        if data.max() not in bins:
            bins = np.append(bins, data.max())
        counts, bins = np.histogram(data, bins)

        return cls(counts, bins)

    def __repr__(self):
        """String representation of the class."""
        return 'DVH(%s, %r bins: [%r:%r] %s, volume: %r %s, name: %r, ' \
            'rx_dose: %d %s)' % \
            (self.dvh_type, self.counts.size, self.bins.min(),
                self.bins.max(), self.dose_units.capitalize(),
                self.volume, self.volume_units.lower(),
                self.name,
                0 if not self.rx_dose else self.rx_dose,
                self.dose_units.capitalize())

    def __eq__(self, other):
        """Comparison method between two DVH objects.

        Parameters
        ----------
        other : DVH
            Other DVH object to compare with

        Returns
        -------
        Bool
            True or False if the DVHs have equal attribs and via numpy.allclose
        """
        attribs = ('dvh_type', 'dose_units', 'volume_units')
        attribs_eq = {k: self.__dict__[k] for k in attribs} == \
            {k: other.__dict__[k] for k in attribs}
        return attribs_eq and \
            np.allclose(self.counts, other.counts) and \
            np.allclose(self.bins, other.bins)

# ============================= DVH properties ============================= #

    @property
    def bincenters(self):
        """Return a numpy array containing the bin centers."""
        return 0.5 * (self.bins[1:] + self.bins[:-1])

    @property
    def differential(self):
        """Return a differential DVH from a cumulative DVH."""
        dvh_type = 'differential'
        if self.dvh_type == dvh_type:
            return self
        else:
            return DVH(**dict(
                self.__dict__,
                counts=np.append(abs(np.diff(self.counts) * -1), [0]),
                dvh_type=dvh_type))

    @property
    def cumulative(self):
        """Return a cumulative DVH from a differential DVH."""
        dvh_type = 'cumulative'
        if self.dvh_type == dvh_type:
            return self
        else:
            return DVH(**dict(
                self.__dict__,
                counts=self.counts[::-1].cumsum()[::-1],
                dvh_type=dvh_type))

    def absolute_dose(self, rx_dose=None, dose_units=abs_dose_units):
        """Return an absolute dose DVH.

        Parameters
        ----------
        rx_dose : number, optional
            Prescription dose value used to normalize dose bins
        dose_units : str, optional
            Units for the absolute dose

        Raises
        ------
        AttributeError
            Description
        """
        if self.dose_units == dose_units:
            return self
        else:
            # Raise an error if no rx_dose defined
            if not self.rx_dose and not rx_dose:
                raise AttributeError("'DVH' has no defined prescription dose.")
            else:
                rxdose = rx_dose if self.rx_dose is None else self.rx_dose
            return DVH(**dict(
                self.__dict__,
                bins=self.bins * rxdose / 100,
                dose_units=dose_units))

    def relative_dose(self, rx_dose=None):
        """Return a relative dose DVH based on a prescription dose.

        Parameters
        ----------
        rx_dose : number, optional
            Prescription dose value used to normalize dose bins

        Raises
        ------
        AttributeError
            Raised if prescription dose was not present either during
            class initialization or passed via argument.
        """
        dose_units = relative_units
        if self.dose_units == dose_units:
            return self
        else:
            # Raise an error if no rx_dose defined
            if not self.rx_dose and not rx_dose:
                raise AttributeError("'DVH' has no defined prescription dose.")
            else:
                rxdose = rx_dose if self.rx_dose is None else self.rx_dose
            return DVH(**dict(
                self.__dict__,
                bins=100 * self.bins / rxdose,
                dose_units=dose_units))

    def absolute_volume(self, volume, volume_units=abs_volume_units):
        """Return an absolute volume DVH.

        Parameters
        ----------
        volume : number
            Absolute volume of the structure
        volume_units : str, optional
            Units for the absolute volume
        """
        if self.volume_units == volume_units:
            return self
        else:
            return DVH(**dict(
                self.__dict__,
                counts=volume * self.counts / 100,
                volume_units=volume_units))

    @property
    def relative_volume(self):
        """Return a relative volume DVH."""
        volume_units = relative_units
        if self.volume_units == relative_units:
            return self
        # Convert back to cumulative before returning a relative volume
        elif self.dvh_type == 'differential':
            return self.cumulative.relative_volume.differential
        else:
            return DVH(**dict(
                self.__dict__,
                counts=100 * self.counts / self.counts.max(),
                volume_units=volume_units))

    @property
    def max(self):
        """Return the maximum dose."""
        diff = self.differential
        # Find the the maximum non-zero dose bin
        return diff.bins[1:][diff.counts > 0][-1]

    @property
    def min(self):
        """Return the minimum dose."""
        diff = self.differential
        # Find the the minimum non-zero dose bin
        return diff.bins[1:][diff.counts > 0][0]

    @property
    def mean(self):
        """Return the mean dose."""
        diff = self.differential
        # Find the area under the differential histogram
        return (diff.bincenters * diff.counts).sum() / diff.counts.sum()

    @property
    def volume(self):
        """Return the volume of the structure."""
        return self.differential.counts.sum()

    def plot(self):
        """Plot the DVH using Matplotlib if present."""
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            print('Matplotlib could not be loaded. Install and try again.')
        else:
            plt.plot(self.bincenters, self.counts, label=self.name)
            # plt.axis([0, self.bins[-1], 0, self.counts[0]])
            plt.xlabel('Dose [%s]' % self.dose_units.capitalize())
            plt.ylabel('Volume [%s]' % self.volume_units.lower())
            if self.name:
                plt.legend(loc='best')
        return self

    def volume_constraint(self, dose, dose_units=None):
        """Calculate the volume that receives at least a specific dose.

        i.e. V100, V150 or V20Gy

        Parameters
        ----------
        dose : number
            Dose value used to determine minimum volume that receives
            this dose. Can either be in relative or absolute dose units.

        Returns
        -------
        number
            Volume in self.volume_units units.
        """
        # Determine whether to lookup relative dose or absolute dose
        if not dose_units:
            dose_bins = self.relative_dose(14).bins
        else:
            dose_bins = self.absolute_dose(14).bins
        index = np.argmin(np.fabs(dose_bins - dose))
        # TODO Add interpolation
        if index >= self.counts.size:
            return DVHValue(0.0, self.volume_units)
        else:
            return DVHValue(self.counts[index], self.volume_units)

    def dose_constraint(self, volume, volume_units=None):
        """Calculate the maximum dose that a specific volume receives.

        i.e. D90, D100 or D2cc

        Parameters
        ----------
        volume : number
            Volume used to determine the maximum dose that the volume receives.
            Can either be in relative or absolute volume units.

        Returns
        -------
        number
            Dose in self.dose_units units.
        """
        # Determine whether to lookup relative volume or absolute volume
        if not volume_units:
            volume_counts = self.relative_volume.counts
        else:
            volume_counts = self.absolute_volume(14).counts
        if volume > volume_counts.max():
            return DVHValue(0.0, self.dose_units)
        # TODO Add interpolation
        return DVHValue(
            self.bins[np.argmin(
                np.fabs(volume_counts - volume))],
            self.dose_units)

    def __getattr__(self, name):
        """Method used to automatically generate dose & volume stats properties.

        Parameters
        ----------
        name : string
            Property name called to determine dose & volume statistics

        Returns
        -------
        number
            Value from the dose or volume statistic calculation.
        """
        # Compile a regex to determine dose & volume statistics
        p = re.compile(r'(\S+)?(D|V){1}(\d+[.]?\d*)(gy|cc)?(?!\S+)',
                       re.IGNORECASE)
        match = re.match(p, name)
        # Return the default attribute if not a dose or volume statistic
        # print(match.groups())
        if not match or match.groups()[0] is not None:
            raise AttributeError("'DVH' has no attribute '%s'" % name)

        # Process the regex match
        c = [x.lower() for x in match.groups() if x]
        if c[0] == ('v'):
            # Volume Constraints (i.e. V100) & return a volume
            if len(c) == 2:
                return self.volume_constraint(int(c[1]))
            # Volume Constraints in abs dose (i.e. V20Gy) & return a volume
            return self.volume_constraint(int(c[1]), c[2])
        elif c[0] == ('d'):
            # Dose Constraints (i.e. D90) & return a dose
            if len(c) == 2:
                return self.dose_constraint(int(c[1]))
            # Dose Constraints in abs volume (i.e. D2cc) & return a dose
            return self.dose_constraint(int(c[1]), c[2])


class DVHValue(object):
    """Class that stores DVH values with the appropriate units."""

    def __init__(self, value, units=''):
        """Initialization for a DVH value that will also store units."""
        self.value = value
        self.units = units

    def __repr__(self):
        """Representation of the DVH value."""
        return "dvh.DVHValue(" + self.value.__repr__() + \
            ", '" + self.units + "')"

    def __str__(self):
        """String representation of the DVH value."""
        if not self.units:
            return str(self.value)
        else:
            return str(self.value) + ' ' + self.units

    def __eq__(self, other):
        """Comparison method between two DVHValue objects.

        Parameters
        ----------
        other : DVHValue
            Other DVHValue object to compare with

        Returns
        -------
        Bool
            True or False if the DVHValues have equal attribs
        """
        attribs_eq = self.units == other.units
        return attribs_eq and \
            np.allclose(self.value, other.value)
