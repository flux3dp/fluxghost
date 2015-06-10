#include <vector>

#include <pcl/point_cloud.h>
#include <pcl/point_types.h>
#include <pcl/features/fpfh_omp.h>
#include <Eigen/Core>


// noise del
typedef pcl::PointCloud<pcl::PointXYZRGB>::Ptr PointCloudXYZRGBPtr;

PointCloudXYZRGBPtr createPointCloudXYZRGB();
void push_backPoint(PointCloudXYZRGBPtr cloud, float x, float y, float z, uint32_t rgb);
int loadPointCloudXYZRGB(const char* file, PointCloudXYZRGBPtr cloud);
void dumpPointCloudXYZRGB(const char* file, PointCloudXYZRGBPtr cloud);

int SOR(PointCloudXYZRGBPtr cloud, int neighbors, float threshold);
int VG(PointCloudXYZRGBPtr cloud);

//normal estimation
typedef pcl::PointCloud<pcl::Normal>::Ptr NormalPtr;
typedef pcl::PointCloud<pcl::PointXYZRGBNormal>::Ptr PointXYZRGBNormalPtr;

NormalPtr createNormalPtr();

int ne(PointCloudXYZRGBPtr cloud, NormalPtr normals);
int ne_viewpoint(PointCloudXYZRGBPtr cloud, NormalPtr normals, std::vector<std::vector<int> >viewp, std::vector<int> step);
PointXYZRGBNormalPtr concatenatePointsNormal(PointCloudXYZRGBPtr cloud, NormalPtr normals);


// registration
// Types

typedef pcl::PointXYZRGBNormal PointNT; // float x, y, z; float normal[3], curvature, rgb
// typedef pcl::PointCloud<PointNT> PointCloudT;
// typedef pcl::PointCloud<PointNT>::Ptr PointCloudTPtr;
typedef pcl::FPFHSignature33 FeatureT;

typedef pcl::FPFHEstimationOMP<PointNT, PointNT, FeatureT> FeatureEstimationT;
typedef pcl::PointCloud<FeatureT> FeatureCloudT;
typedef pcl::PointCloud<FeatureT>::Ptr FeatureCloudTPtr;

// PointCloudTPtr createPointCloudPointNormal();
int loadPointNT(const char* file, PointXYZRGBNormalPtr cloud);
void dumpPointNT(const char* file, PointXYZRGBNormalPtr cloud);

int downsample(PointXYZRGBNormalPtr cloud, float leaf);
int FE(PointXYZRGBNormalPtr cloud, FeatureCloudTPtr cloud_features, float radius);
int SCP(PointXYZRGBNormalPtr object, FeatureCloudTPtr object_features, PointXYZRGBNormalPtr scene, FeatureCloudTPtr scene_features, Eigen::Matrix4f &transformation, float leaf);

